import json
import sys
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowforge_ai.database import get_db
from flowforge_ai.models import (
    Job, Queue, Batch, CronConfig, AIDiagnostics, JobLog, Project, ProjectMember
)
from flowforge_ai.control_plane.auth.auth_service import get_current_user, RoleChecker

router = APIRouter(prefix="/api/v1/projects/{project_id}")

# --- Pydantic Schemas ---

class QueueCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    concurrency_limit: int = Field(default=1, gt=0)

class QueueOut(BaseModel):
    id: str
    project_id: str
    name: str
    concurrency_limit: int
    created_at: datetime
    model_config = {"from_attributes": True}

class JobSubmit(BaseModel):
    queue_name: str = Field(..., min_length=1)
    target_handler: str = Field(..., min_length=1, max_length=255)
    payload: dict = Field(default_factory=dict)
    priority: int = Field(default=0)
    retries: int = Field(default=0, ge=0)
    delay_seconds: int = Field(default=0, ge=0)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, v):
        serialized = json.dumps(v)
        if sys.getsizeof(serialized) > 102400:
            raise ValueError("Job payload cannot exceed 100 KB size limit.")
        return v

class JobOut(BaseModel):
    id: str
    status: str
    queue_id: str
    target_handler: str
    payload: Optional[str] = None
    priority: int
    retries_total: int
    retries_remaining: int
    created_at: datetime
    scheduled_for: datetime
    claimed_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    model_config = {"from_attributes": True}

class JobCancelOut(BaseModel):
    id: str
    status: str
    model_config = {"from_attributes": True}

class BatchCreate(BaseModel):
    jobs: list[JobSubmit] = Field(..., min_length=1)
    callback_handler: Optional[str] = None
    callback_payload: Optional[dict] = None
    callback_trigger_condition: str = Field(default="ALWAYS")

    @field_validator("callback_trigger_condition")
    @classmethod
    def validate_trigger(cls, v):
        allowed = {"ALWAYS", "ON_SUCCESS", "ON_FAILURE", "NEVER"}
        if v not in allowed:
            raise ValueError(f"callback_trigger_condition must be one of {allowed}")
        return v

class BatchOut(BaseModel):
    batch_id: str
    status: str
    total_jobs: int
    created_at: datetime
    model_config = {"from_attributes": True}

class BatchDetailOut(BaseModel):
    batch_id: str
    status: str
    progress: dict
    created_at: datetime
    finished_at: Optional[datetime] = None

class CronCreate(BaseModel):
    cron_expression: str = Field(..., min_length=5, max_length=100)
    queue_name: str = Field(..., min_length=1)
    target_handler: str = Field(..., min_length=1, max_length=255)
    payload: dict = Field(default_factory=dict)
    missed_run_policy: str = Field(default="RUN_ONCE")

    @field_validator("missed_run_policy")
    @classmethod
    def validate_policy(cls, v):
        allowed = {"RUN_ONCE", "FORCE_RUN", "SKIP"}
        if v not in allowed:
            raise ValueError(f"missed_run_policy must be one of {allowed}")
        return v

class CronOut(BaseModel):
    id: str
    cron_expression: str
    missed_run_policy: str
    next_scheduled_at: Optional[datetime] = None
    model_config = {"from_attributes": True}

class DLQJobOut(BaseModel):
    id: str
    queue_id: str
    target_handler: str
    finished_at: Optional[datetime] = None
    retries_total: int
    model_config = {"from_attributes": True}

class DiagnosticsOut(BaseModel):
    job_id: str
    diagnostic_status: str
    error_summary: Optional[str] = None
    root_cause: Optional[str] = None
    remediation_suggestion: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# --- Helper: verify project membership ---
def _verify_membership(db: Session, project_id: str, user, roles: list[str]) -> ProjectMember:
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user.id
    ).first()
    if not member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")
    if member.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires one of: {', '.join(roles)}")
    return member


# ==================== QUEUE ENDPOINTS ====================

@router.post("/queues", response_model=QueueOut, status_code=status.HTTP_201_CREATED)
def create_queue(
    project_id: str,
    queue_data: QueueCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER"])

    # Check project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # Check duplicate queue name
    existing = db.query(Queue).filter(
        Queue.project_id == project_id,
        Queue.name == queue_data.name
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Queue name already exists in project")

    queue = Queue(
        project_id=project_id,
        name=queue_data.name,
        concurrency_limit=queue_data.concurrency_limit
    )
    db.add(queue)
    db.commit()
    db.refresh(queue)
    return queue


@router.get("/queues", response_model=list[QueueOut])
def list_queues(
    project_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER", "OPERATOR"])
    queues = db.query(Queue).filter(Queue.project_id == project_id).all()
    return queues


# ==================== JOB ENDPOINTS ====================

@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def submit_job(
    project_id: str,
    job_data: JobSubmit,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER"])

    # Resolve queue by name
    queue = db.query(Queue).filter(
        Queue.project_id == project_id,
        Queue.name == job_data.queue_name
    ).first()
    if not queue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Queue '{job_data.queue_name}' not found")

    # Idempotency check: if key is provided, look for existing job
    if idempotency_key:
        existing_job = db.query(Job).filter(
            Job.project_id == project_id,
            Job.idempotency_key == idempotency_key
        ).first()
        if existing_job:
            # Return existing job with 200 OK (not 201)
            return existing_job

    # Calculate scheduled_for
    scheduled_for = datetime.utcnow()
    if job_data.delay_seconds > 0:
        scheduled_for = scheduled_for + timedelta(seconds=job_data.delay_seconds)

    payload_str = json.dumps(job_data.payload)

    job = Job(
        project_id=project_id,
        queue_id=queue.id,
        target_handler=job_data.target_handler,
        payload=payload_str,
        status="QUEUED",
        priority=job_data.priority,
        retries_total=job_data.retries,
        retries_remaining=job_data.retries,
        idempotency_key=idempotency_key,
        scheduled_for=scheduled_for,
    )
    db.add(job)

    try:
        db.commit()
        db.refresh(job)
    except IntegrityError:
        db.rollback()
        # Concurrent idempotency race: another request inserted first
        if idempotency_key:
            existing_job = db.query(Job).filter(
                Job.project_id == project_id,
                Job.idempotency_key == idempotency_key
            ).first()
            if existing_job:
                return existing_job
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create job")

    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(
    project_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER", "OPERATOR"])

    job = db.query(Job).filter(
        Job.project_id == project_id,
        Job.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobCancelOut)
def cancel_job(
    project_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER"])

    job = db.query(Job).filter(
        Job.project_id == project_id,
        Job.id == job_id
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # Only QUEUED, CLAIMED, or RUNNING jobs can be cancelled
    if job.status not in ("QUEUED", "CLAIMED", "RUNNING"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in '{job.status}' state"
        )

    job.status = "CANCELLED"
    job.worker_id = None
    job.ownership_token = None
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


# ==================== BATCH ENDPOINTS ====================

@router.post("/batches", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create_batch(
    project_id: str,
    batch_data: BatchCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER"])

    callback_payload_str = json.dumps(batch_data.callback_payload) if batch_data.callback_payload else None

    batch = Batch(
        project_id=project_id,
        status="RUNNING",
        callback_handler=batch_data.callback_handler,
        callback_payload=callback_payload_str,
        callback_trigger_condition=batch_data.callback_trigger_condition,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    # Create child jobs
    for job_data in batch_data.jobs:
        queue = db.query(Queue).filter(
            Queue.project_id == project_id,
            Queue.name == job_data.queue_name
        ).first()
        if not queue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Queue '{job_data.queue_name}' not found"
            )

        scheduled_for = datetime.utcnow()
        if job_data.delay_seconds > 0:
            scheduled_for = scheduled_for + timedelta(seconds=job_data.delay_seconds)

        job = Job(
            project_id=project_id,
            queue_id=queue.id,
            batch_id=batch.id,
            target_handler=job_data.target_handler,
            payload=json.dumps(job_data.payload),
            status="QUEUED",
            priority=job_data.priority,
            retries_total=job_data.retries,
            retries_remaining=job_data.retries,
            scheduled_for=scheduled_for,
        )
        db.add(job)

    db.commit()

    total_jobs = db.query(Job).filter(Job.batch_id == batch.id).count()

    return BatchOut(
        batch_id=batch.id,
        status=batch.status,
        total_jobs=total_jobs,
        created_at=batch.created_at
    )


@router.get("/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(
    project_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER", "OPERATOR"])

    batch = db.query(Batch).filter(
        Batch.project_id == project_id,
        Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

    # Calculate progress
    child_jobs = db.query(Job).filter(Job.batch_id == batch_id).all()
    progress = {
        "total": len(child_jobs),
        "queued": sum(1 for j in child_jobs if j.status == "QUEUED"),
        "claimed": sum(1 for j in child_jobs if j.status == "CLAIMED"),
        "running": sum(1 for j in child_jobs if j.status == "RUNNING"),
        "completed": sum(1 for j in child_jobs if j.status == "COMPLETED"),
        "failed_dlq": sum(1 for j in child_jobs if j.status in ("FAILED", "DLQ")),
        "cancelled": sum(1 for j in child_jobs if j.status == "CANCELLED"),
    }

    return BatchDetailOut(
        batch_id=batch.id,
        status=batch.status,
        progress=progress,
        created_at=batch.created_at,
        finished_at=batch.finished_at
    )


# ==================== CRON ENDPOINTS ====================

@router.post("/cron", response_model=CronOut, status_code=status.HTTP_201_CREATED)
def create_cron(
    project_id: str,
    cron_data: CronCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER"])

    # Resolve queue by name
    queue = db.query(Queue).filter(
        Queue.project_id == project_id,
        Queue.name == cron_data.queue_name
    ).first()
    if not queue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Queue '{cron_data.queue_name}' not found")

    cron_config = CronConfig(
        project_id=project_id,
        queue_id=queue.id,
        cron_expression=cron_data.cron_expression,
        target_handler=cron_data.target_handler,
        payload=json.dumps(cron_data.payload),
        missed_run_policy=cron_data.missed_run_policy,
    )
    db.add(cron_config)
    db.commit()
    db.refresh(cron_config)
    return cron_config


@router.delete("/cron/{cron_id}")
def delete_cron(
    project_id: str,
    cron_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER"])

    cron_config = db.query(CronConfig).filter(
        CronConfig.project_id == project_id,
        CronConfig.id == cron_id
    ).first()
    if not cron_config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cron configuration not found")

    db.delete(cron_config)
    db.commit()
    return {"message": "Cron configuration deleted successfully."}


# ==================== DLQ ENDPOINTS ====================

@router.get("/dlq", response_model=list[DLQJobOut])
def list_dlq_jobs(
    project_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER", "OPERATOR"])

    dlq_jobs = db.query(Job).filter(
        Job.project_id == project_id,
        Job.status == "DLQ"
    ).all()
    return dlq_jobs


@router.post("/dlq/{job_id}/requeue", response_model=JobOut)
def requeue_dlq_job(
    project_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER"])

    job = db.query(Job).filter(
        Job.project_id == project_id,
        Job.id == job_id,
        Job.status == "DLQ"
    ).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DLQ job not found")

    job.status = "QUEUED"
    job.retries_remaining = job.retries_total
    job.worker_id = None
    job.ownership_token = None
    job.finished_at = None
    job.claimed_at = None
    job.started_at = None
    job.scheduled_for = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


# ==================== DIAGNOSTICS ENDPOINT ====================

@router.get("/jobs/{job_id}/diagnostics", response_model=DiagnosticsOut)
def get_diagnostics(
    project_id: str,
    job_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    _verify_membership(db, project_id, current_user, ["OWNER", "DEVELOPER", "OPERATOR"])

    diag = db.query(AIDiagnostics).filter(
        AIDiagnostics.project_id == project_id,
        AIDiagnostics.job_id == job_id
    ).first()
    if not diag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No diagnostics found for this job")
    return diag
