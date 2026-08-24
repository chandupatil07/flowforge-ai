"""
Worker registration, heartbeat, and status endpoints.
Workers are system-wide infrastructure; they are not project-scoped.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from flowforge_ai.database import get_db
from flowforge_ai.models import Worker, generate_uuid

router = APIRouter(prefix="/api/v1/workers", tags=["workers"])


# --- Pydantic Schemas ---

class WorkerRegister(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    capacity: int = Field(default=1, gt=0)

class WorkerOut(BaseModel):
    id: str
    hostname: str
    capacity: int
    status: str
    last_heartbeat_at: datetime
    registered_at: datetime
    model_config = {"from_attributes": True}

class HeartbeatOut(BaseModel):
    id: str
    status: str
    last_heartbeat_at: datetime


# ==================== WORKER ENDPOINTS ====================

@router.post("/register", response_model=WorkerOut, status_code=status.HTTP_201_CREATED)
def register_worker(
    worker_data: WorkerRegister,
    db: Session = Depends(get_db),
):
    """Register a new worker node in the cluster."""
    worker_id = generate_uuid()

    worker = Worker(
        id=worker_id,
        hostname=worker_data.hostname,
        capacity=worker_data.capacity,
        status="ACTIVE",
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


@router.post("/{worker_id}/heartbeat", response_model=HeartbeatOut)
def worker_heartbeat(
    worker_id: str,
    db: Session = Depends(get_db),
):
    """Update the worker's heartbeat timestamp to prove liveness."""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    if worker.status == "OFFLINE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Worker has been marked OFFLINE by the Reaper. Re-register to rejoin."
        )

    worker.last_heartbeat_at = datetime.utcnow()
    db.commit()
    db.refresh(worker)
    return HeartbeatOut(
        id=worker.id,
        status=worker.status,
        last_heartbeat_at=worker.last_heartbeat_at
    )


@router.get("", response_model=list[WorkerOut])
def list_workers(
    db: Session = Depends(get_db),
):
    """List all registered workers."""
    workers = db.query(Worker).all()
    return workers


@router.get("/{worker_id}", response_model=WorkerOut)
def get_worker(
    worker_id: str,
    db: Session = Depends(get_db),
):
    """Get details about a specific worker."""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    return worker


@router.post("/{worker_id}/deregister")
def deregister_worker(
    worker_id: str,
    db: Session = Depends(get_db),
):
    """Gracefully deregister a worker."""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")

    worker.status = "OFFLINE"
    db.commit()
    return {"message": f"Worker {worker_id} deregistered successfully."}
