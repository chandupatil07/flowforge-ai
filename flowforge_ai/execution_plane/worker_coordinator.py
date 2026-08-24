"""
Worker Coordinator — Atomic Job Claiming Engine.

Implements the deterministic queue locking + job claiming CTE pattern
described in docs/04-api-contracts-and-database-design.md.

For SQLite testing: uses simplified claiming since SQLite lacks
FOR UPDATE / SKIP LOCKED support.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import text, and_, or_
from sqlalchemy.orm import Session

from flowforge_ai.models import Job, Queue, Worker

logger = logging.getLogger("flowforge_ai.worker_coordinator")


def claim_job(db: Session, worker_id: str) -> Optional[Job]:
    """
    Atomically claim the highest-priority eligible job for the given worker.

    Algorithm (simplified for SQLite compatibility):
    1. Find all queues that have QUEUED jobs with scheduled_for <= NOW.
    2. For each queue (ordered by queue.id for deterministic lock ordering),
       count active jobs (CLAIMED + RUNNING).
    3. If active_count < concurrency_limit, claim the highest-priority QUEUED job.
    4. Generate a fencing token (ownership_token) and transition status to CLAIMED.

    Returns the claimed Job or None if no eligible job was found.
    """
    now = datetime.utcnow()
    ownership_token = str(uuid.uuid4())

    # Step 1: Find queues with pending jobs
    queues_with_pending = (
        db.query(Queue)
        .join(Job, Job.queue_id == Queue.id)
        .filter(
            Job.status == "QUEUED",
            Job.scheduled_for <= now
        )
        .distinct()
        .order_by(Queue.id)  # Deterministic ordering to prevent deadlocks
        .all()
    )

    for queue in queues_with_pending:
        # Step 2: Count active jobs in this queue
        active_count = (
            db.query(Job)
            .filter(
                Job.queue_id == queue.id,
                Job.status.in_(["CLAIMED", "RUNNING"])
            )
            .count()
        )

        # Step 3: Check concurrency capacity
        if active_count >= queue.concurrency_limit:
            continue

        # Step 4: Find the highest-priority eligible job
        eligible_job = (
            db.query(Job)
            .filter(
                Job.queue_id == queue.id,
                Job.status == "QUEUED",
                Job.scheduled_for <= now
            )
            .order_by(Job.priority.desc(), Job.created_at.asc())
            .first()
        )

        if eligible_job:
            # Atomically claim the job
            eligible_job.status = "CLAIMED"
            eligible_job.worker_id = worker_id
            eligible_job.ownership_token = ownership_token
            eligible_job.claimed_at = now
            db.commit()
            db.refresh(eligible_job)
            logger.info(
                f"Worker {worker_id} claimed job {eligible_job.id} "
                f"(queue={queue.name}, token={ownership_token})"
            )
            return eligible_job

    return None


def start_job(db: Session, job_id: str, worker_id: str, ownership_token: str) -> Optional[Job]:
    """
    Transition a CLAIMED job to RUNNING, verifying ownership via fencing token.

    Returns the updated Job if the fencing token matches, or None if stale.
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.worker_id == worker_id,
        Job.ownership_token == ownership_token,
        Job.status == "CLAIMED"
    ).first()

    if not job:
        logger.warning(
            f"Worker {worker_id} cannot start job {job_id}: "
            f"ownership token mismatch or job no longer CLAIMED."
        )
        return None

    job.status = "RUNNING"
    job.started_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    logger.info(f"Job {job_id} is now RUNNING (worker={worker_id})")
    return job


def complete_job(
    db: Session,
    job_id: str,
    worker_id: str,
    ownership_token: str,
    log_content: Optional[str] = None
) -> Optional[Job]:
    """
    Transition a RUNNING job to COMPLETED, verifying fencing token.

    If log_content is provided, a JobLog record is created.
    Returns the updated Job or None if the ownership token is stale.
    """
    from flowforge_ai.models import JobLog

    job = db.query(Job).filter(
        Job.id == job_id,
        Job.worker_id == worker_id,
        Job.ownership_token == ownership_token,
        Job.status == "RUNNING"
    ).first()

    if not job:
        logger.warning(
            f"Worker {worker_id} cannot complete job {job_id}: "
            f"ownership token mismatch or job no longer RUNNING."
        )
        return None

    job.status = "COMPLETED"
    job.finished_at = datetime.utcnow()

    if log_content:
        # Truncate to 100KB
        if len(log_content) > 102400:
            log_content = log_content[:102400]
        job_log = JobLog(
            job_id=job_id,
            content=log_content,
        )
        db.add(job_log)

    db.commit()
    db.refresh(job)
    logger.info(f"Job {job_id} COMPLETED (worker={worker_id})")
    return job


def fail_job(
    db: Session,
    job_id: str,
    worker_id: str,
    ownership_token: str,
    log_content: Optional[str] = None
) -> Optional[Job]:
    """
    Handle job failure: retry if retries remaining, else move to DLQ.
    Verifies fencing token ownership before any state transition.

    Returns the updated Job or None if the ownership token is stale.
    """
    from flowforge_ai.models import JobLog

    job = db.query(Job).filter(
        Job.id == job_id,
        Job.worker_id == worker_id,
        Job.ownership_token == ownership_token,
        Job.status == "RUNNING"
    ).first()

    if not job:
        logger.warning(
            f"Worker {worker_id} cannot fail job {job_id}: "
            f"ownership token mismatch or job no longer RUNNING."
        )
        return None

    # Save logs
    if log_content:
        if len(log_content) > 102400:
            log_content = log_content[:102400]
        # Check if log already exists for this job
        existing_log = db.query(JobLog).filter(JobLog.job_id == job_id).first()
        if existing_log:
            existing_log.content = log_content
        else:
            job_log = JobLog(job_id=job_id, content=log_content)
            db.add(job_log)

    if job.retries_remaining > 0:
        # Re-queue for retry
        job.retries_remaining -= 1
        job.status = "QUEUED"
        job.worker_id = None
        job.ownership_token = None
        job.claimed_at = None
        job.started_at = None
        job.finished_at = None
        job.scheduled_for = datetime.utcnow()
        logger.info(
            f"Job {job_id} FAILED, retrying ({job.retries_remaining} retries left)"
        )
    else:
        # Move to DLQ
        job.status = "DLQ"
        job.finished_at = datetime.utcnow()
        logger.info(f"Job {job_id} exhausted retries, moved to DLQ")

    db.commit()
    db.refresh(job)
    return job
