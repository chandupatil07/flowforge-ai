"""
Reaper Daemon — Worker Liveness Monitor & Orphan Recovery.

Periodically sweeps the workers table for stale heartbeats,
marks them OFFLINE, and reclaims or DLQs orphaned jobs.

Also handles batch completion evaluation after job state changes.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from flowforge_ai.models import Worker, Job, Batch

logger = logging.getLogger("flowforge_ai.reaper")

# Default heartbeat timeout: workers not heard from in this many seconds are considered dead
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 30


def sweep_stale_workers(
    db: Session,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
) -> list[str]:
    """
    Find workers whose last_heartbeat_at exceeds the timeout threshold.
    Transition them to OFFLINE status.

    Returns list of worker IDs that were marked OFFLINE.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=heartbeat_timeout_seconds)

    stale_workers = db.query(Worker).filter(
        Worker.status == "ACTIVE",
        Worker.last_heartbeat_at < cutoff
    ).all()

    offlined_ids = []
    for worker in stale_workers:
        worker.status = "OFFLINE"
        offlined_ids.append(worker.id)
        logger.warning(
            f"Reaper: Worker {worker.id} ({worker.hostname}) marked OFFLINE "
            f"(last heartbeat: {worker.last_heartbeat_at})"
        )

    if offlined_ids:
        db.commit()

    return offlined_ids


def reclaim_orphaned_jobs(
    db: Session,
    offlined_worker_ids: list[str]
) -> dict:
    """
    Find jobs owned by offlined workers and either:
    - Re-queue them if retries_remaining > 0
    - Move them to DLQ if no retries remaining

    Revokes ownership_token on all reclaimed jobs.

    Returns dict with counts: {"requeued": N, "dlq": N}
    """
    if not offlined_worker_ids:
        return {"requeued": 0, "dlq": 0}

    orphaned_jobs = db.query(Job).filter(
        Job.worker_id.in_(offlined_worker_ids),
        Job.status.in_(["CLAIMED", "RUNNING"])
    ).all()

    requeued = 0
    dlq = 0

    for job in orphaned_jobs:
        # Revoke ownership
        job.worker_id = None
        job.ownership_token = None

        if job.retries_remaining > 0:
            job.retries_remaining -= 1
            job.status = "QUEUED"
            job.claimed_at = None
            job.started_at = None
            job.finished_at = None
            job.scheduled_for = datetime.utcnow()
            requeued += 1
            logger.info(
                f"Reaper: Job {job.id} re-queued "
                f"({job.retries_remaining} retries left)"
            )
        else:
            job.status = "DLQ"
            job.finished_at = datetime.utcnow()
            dlq += 1
            logger.info(f"Reaper: Job {job.id} moved to DLQ (no retries left)")

    if orphaned_jobs:
        db.commit()

    return {"requeued": requeued, "dlq": dlq}


def evaluate_batch_completion(db: Session, batch_id: str) -> Optional[Batch]:
    """
    Check if all child jobs of a batch are in terminal states.
    If so, update the batch status to SUCCESS or FAILED.

    Terminal job states: COMPLETED, FAILED, CANCELLED, DLQ
    Batch SUCCESS: all children COMPLETED.
    Batch FAILED: at least one child is FAILED, CANCELLED, or DLQ.

    Returns the updated Batch or None if batch is not yet terminal.
    """
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch or batch.status != "RUNNING":
        return None

    child_jobs = db.query(Job).filter(Job.batch_id == batch_id).all()
    if not child_jobs:
        return None

    terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "DLQ"}
    non_terminal = [j for j in child_jobs if j.status not in terminal_states]

    if non_terminal:
        # Not all children are terminal yet
        return None

    # All children terminal — determine batch outcome
    all_completed = all(j.status == "COMPLETED" for j in child_jobs)

    if all_completed:
        batch.status = "SUCCESS"
    else:
        batch.status = "FAILED"

    batch.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(batch)

    logger.info(
        f"Batch {batch_id} completed with status={batch.status} "
        f"({len(child_jobs)} jobs)"
    )

    # Handle callback trigger evaluation
    _evaluate_callback(db, batch, child_jobs)

    return batch


def _evaluate_callback(db: Session, batch: Batch, child_jobs: list[Job]):
    """
    Evaluate whether the batch callback should be triggered based on
    the callback_trigger_condition.
    """
    if not batch.callback_handler:
        return

    condition = batch.callback_trigger_condition
    should_trigger = False

    if condition == "ALWAYS":
        should_trigger = True
    elif condition == "ON_SUCCESS" and batch.status == "SUCCESS":
        should_trigger = True
    elif condition == "ON_FAILURE" and batch.status == "FAILED":
        should_trigger = True
    elif condition == "NEVER":
        should_trigger = False

    if should_trigger:
        import json
        # Create callback job in the same project
        callback_payload = batch.callback_payload or "{}"

        # Find a queue for the callback (use the first child job's queue)
        queue_id = child_jobs[0].queue_id if child_jobs else None
        if not queue_id:
            logger.warning(f"Batch {batch.id}: no queue found for callback job")
            return

        callback_job = Job(
            project_id=batch.project_id,
            queue_id=queue_id,
            batch_id=None,
            target_handler=batch.callback_handler,
            payload=callback_payload,
            status="QUEUED",
            priority=0,
            retries_total=0,
            retries_remaining=0,
            scheduled_for=datetime.utcnow(),
        )
        db.add(callback_job)
        db.commit()
        db.refresh(callback_job)

        # Link callback job to batch
        batch.callback_job_id = callback_job.id
        db.commit()

        logger.info(
            f"Batch {batch.id}: callback job {callback_job.id} created "
            f"(handler={batch.callback_handler}, condition={condition})"
        )


def run_reaper_sweep(
    db: Session,
    heartbeat_timeout_seconds: int = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
) -> dict:
    """
    Run a full reaper sweep cycle:
    1. Mark stale workers OFFLINE
    2. Reclaim orphaned jobs
    3. Evaluate any affected batches

    Returns summary dict.
    """
    offlined = sweep_stale_workers(db, heartbeat_timeout_seconds)
    reclaim_result = reclaim_orphaned_jobs(db, offlined)

    # Evaluate batch completions for jobs that just became terminal
    affected_batch_ids = set()
    if offlined:
        dlq_jobs = db.query(Job).filter(
            Job.status.in_(["DLQ", "COMPLETED", "FAILED"]),
            Job.batch_id.isnot(None),
        ).all()
        for job in dlq_jobs:
            affected_batch_ids.add(job.batch_id)

    batches_completed = 0
    for batch_id in affected_batch_ids:
        result = evaluate_batch_completion(db, batch_id)
        if result:
            batches_completed += 1

    return {
        "workers_offlined": len(offlined),
        "jobs_requeued": reclaim_result["requeued"],
        "jobs_dlq": reclaim_result["dlq"],
        "batches_completed": batches_completed,
    }
