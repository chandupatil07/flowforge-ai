import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, foreign
from sqlalchemy.sql import func
from flowforge_ai.database import Base

# Helper to support UUID across both SQLite (fallback) and PostgreSQL
def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    memberships = relationship("ProjectMember", back_populates="user", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    queues = relationship("Queue", back_populates="project", cascade="all, delete-orphan")
    batches = relationship("Batch", back_populates="project", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="project", cascade="all, delete-orphan")
    cron_configs = relationship("CronConfig", back_populates="project", cascade="all, delete-orphan")
    ai_diagnostics = relationship("AIDiagnostics", primaryjoin="Project.id == foreign(AIDiagnostics.project_id)", back_populates="project", cascade="all, delete-orphan")

class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(50), nullable=False)  # OWNER, DEVELOPER, OPERATOR

    project = relationship("Project", back_populates="members")
    user = relationship("User", back_populates="memberships")

    __table_args__ = (
        CheckConstraint(role.in_(["OWNER", "DEVELOPER", "OPERATOR"]), name="chk_project_member_role"),
    )

class Queue(Base):
    __tablename__ = "queues"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    concurrency_limit = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    project = relationship("Project", back_populates="queues")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_queues_project_name"),
        UniqueConstraint("project_id", "id", name="uq_queues_project_id"),
        CheckConstraint("concurrency_limit > 0", name="chk_queues_concurrency_limit"),
    )

class Batch(Base):
    __tablename__ = "batches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False, default="RUNNING")  # RUNNING, SUCCESS, FAILED
    callback_handler = Column(String(255), nullable=True)
    callback_payload = Column(Text, nullable=True)  # Stored as Text to support SQLite fallback easily
    callback_trigger_condition = Column(String(50), nullable=False, default="ALWAYS")  # ALWAYS, ON_SUCCESS, ON_FAILURE, NEVER
    callback_job_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="batches")

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_batches_project_id"),
        CheckConstraint(status.in_(["RUNNING", "SUCCESS", "FAILED"]), name="chk_batches_status"),
        CheckConstraint(callback_trigger_condition.in_(["ALWAYS", "ON_SUCCESS", "ON_FAILURE", "NEVER"]), name="chk_batches_callback_condition"),
        # Project-scoped callback job foreign key constraint (Preserving non-null project_id invariant)
        ForeignKeyConstraint(
            ["project_id", "callback_job_id"],
            ["jobs.project_id", "jobs.id"],
            name="fk_batches_callback_job",
            ondelete="SET NULL"
        ),
    )

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    queue_id = Column(String(36), nullable=False)
    batch_id = Column(String(36), nullable=True)
    cron_config_id = Column(String(36), nullable=True)
    target_handler = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False)  # Stored as Text to support SQLite fallback easily
    status = Column(String(50), nullable=False, default="QUEUED")  # QUEUED, CLAIMED, RUNNING, COMPLETED, FAILED, CANCELLED, DLQ
    priority = Column(Integer, nullable=False, default=0)
    retries_total = Column(Integer, nullable=False, default=0)
    retries_remaining = Column(Integer, nullable=False, default=0)
    worker_id = Column(String(36), ForeignKey("workers.id", ondelete="SET NULL"), nullable=True)
    ownership_token = Column(String(36), nullable=True)
    idempotency_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    scheduled_for = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="jobs")

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_jobs_project_id"),
        UniqueConstraint("project_id", "idempotency_key", name="uq_jobs_idempotency"),
        UniqueConstraint("cron_config_id", "scheduled_for", name="uq_jobs_cron_occurrence"),
        CheckConstraint(status.in_(["QUEUED", "CLAIMED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "DLQ"]), name="chk_jobs_status"),
        CheckConstraint("retries_total >= 0 AND retries_remaining >= 0", name="chk_jobs_retries_bounds"),
        CheckConstraint("retries_remaining <= retries_total", name="chk_jobs_retries_remaining_limit"),
        # Composite FKs enforcing project-scoped reference consistency
        ForeignKeyConstraint(
            ["project_id", "queue_id"],
            ["queues.project_id", "queues.id"],
            name="fk_jobs_project_queue",
            ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["project_id", "batch_id"],
            ["batches.project_id", "batches.id"],
            name="fk_jobs_project_batch",
            ondelete="SET NULL"
        ),
        ForeignKeyConstraint(
            ["project_id", "cron_config_id"],
            ["cron_configs.project_id", "cron_configs.id"],
            name="fk_jobs_project_cron_config",
            ondelete="SET NULL"
        ),
    )

class CronConfig(Base):
    __tablename__ = "cron_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    queue_id = Column(String(36), nullable=False)
    cron_expression = Column(String(100), nullable=False)
    target_handler = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False)  # Stored as Text to support SQLite fallback easily
    missed_run_policy = Column(String(50), nullable=False, default="RUN_ONCE")  # RUN_ONCE, FORCE_RUN, SKIP
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_scheduled_at = Column(DateTime(timezone=True), nullable=True)
    next_scheduled_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="cron_configs")

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_cron_configs_project_id"),
        CheckConstraint(missed_run_policy.in_(["RUN_ONCE", "FORCE_RUN", "SKIP"]), name="chk_cron_configs_missed_run_policy"),
        ForeignKeyConstraint(
            ["project_id", "queue_id"],
            ["queues.project_id", "queues.id"],
            name="fk_cron_configs_project_queue",
            ondelete="RESTRICT"
        ),
    )

class Worker(Base):
    __tablename__ = "workers"

    id = Column(String(36), primary_key=True)
    hostname = Column(String(255), nullable=False)
    capacity = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="ACTIVE")  # ACTIVE, OFFLINE
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    registered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("capacity > 0", name="chk_workers_capacity"),
        CheckConstraint(status.in_(["ACTIVE", "OFFLINE"]), name="chk_workers_status"),
    )

class JobLog(Base):
    __tablename__ = "job_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("length(content) <= 102400", name="chk_job_logs_length"),
    )

class AIDiagnostics(Base):
    __tablename__ = "ai_diagnostics"

    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    project_id = Column(String(36), nullable=False)
    diagnostic_status = Column(String(50), nullable=False, default="NOT_REQUESTED")  # NOT_REQUESTED, ANALYZING, COMPLETED, FAILED, UNAVAILABLE
    error_summary = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    remediation_suggestion = Column(Text, nullable=True)
    analyzed_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", primaryjoin="Project.id == foreign(AIDiagnostics.project_id)", back_populates="ai_diagnostics")

    __table_args__ = (
        CheckConstraint(diagnostic_status.in_(["NOT_REQUESTED", "ANALYZING", "COMPLETED", "FAILED", "UNAVAILABLE"]), name="chk_ai_diagnostics_status"),
        ForeignKeyConstraint(
            ["project_id", "job_id"],
            ["jobs.project_id", "jobs.id"],
            name="fk_ai_diagnostics_project_job",
            ondelete="CASCADE"
        ),
    )
