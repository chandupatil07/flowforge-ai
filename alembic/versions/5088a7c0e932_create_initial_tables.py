"""create_initial_tables

Revision ID: 5088a7c0e932
Revises: 
Create Date: 2026-08-22 18:05:50.898846

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5088a7c0e932'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema in correct dependency order."""
    
    # 1. users
    op.create_table('users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    
    # 2. projects
    op.create_table('projects',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 3. project_members (depends on projects, users)
    op.create_table('project_members',
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.CheckConstraint("role IN ('OWNER', 'DEVELOPER', 'OPERATOR')", name='chk_project_member_role'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('project_id', 'user_id')
    )
    
    # 4. workers
    op.create_table('workers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('hostname', sa.String(length=255), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'OFFLINE')", name='chk_workers_status'),
        sa.CheckConstraint('capacity > 0', name='chk_workers_capacity'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # 5. queues (depends on projects)
    op.create_table('queues',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('concurrency_limit', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('concurrency_limit > 0', name='chk_queues_concurrency_limit'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'id', name='uq_queues_project_id'),
        sa.UniqueConstraint('project_id', 'name', name='uq_queues_project_name')
    )
    
    # 6. cron_configs (depends on projects, queues)
    op.create_table('cron_configs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('queue_id', sa.String(length=36), nullable=False),
        sa.Column('cron_expression', sa.String(length=100), nullable=False),
        sa.Column('target_handler', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('missed_run_policy', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('last_scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("missed_run_policy IN ('RUN_ONCE', 'FORCE_RUN', 'SKIP')", name='chk_cron_configs_missed_run_policy'),
        sa.ForeignKeyConstraint(['project_id', 'queue_id'], ['queues.project_id', 'queues.id'], name='fk_cron_configs_project_queue', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'id', name='uq_cron_configs_project_id')
    )
    
    # 7. batches (depends on projects, does NOT define callback_job_id FK inline due to dependency cycle)
    op.create_table('batches',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('callback_handler', sa.String(length=255), nullable=True),
        sa.Column('callback_payload', sa.Text(), nullable=True),
        sa.Column('callback_trigger_condition', sa.String(length=50), nullable=False),
        sa.Column('callback_job_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("callback_trigger_condition IN ('ALWAYS', 'ON_SUCCESS', 'ON_FAILURE', 'NEVER')", name='chk_batches_callback_condition'),
        sa.CheckConstraint("status IN ('RUNNING', 'SUCCESS', 'FAILED')", name='chk_batches_status'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'id', name='uq_batches_project_id')
    )
    
    # 8. jobs (depends on projects, queues, batches, cron_configs, workers)
    op.create_table('jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('queue_id', sa.String(length=36), nullable=False),
        sa.Column('batch_id', sa.String(length=36), nullable=True),
        sa.Column('cron_config_id', sa.String(length=36), nullable=True),
        sa.Column('target_handler', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('retries_total', sa.Integer(), nullable=False),
        sa.Column('retries_remaining', sa.Integer(), nullable=False),
        sa.Column('worker_id', sa.String(length=36), nullable=True),
        sa.Column('ownership_token', sa.String(length=36), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('QUEUED', 'CLAIMED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'DLQ')", name='chk_jobs_status'),
        sa.CheckConstraint('retries_remaining <= retries_total', name='chk_jobs_retries_remaining_limit'),
        sa.CheckConstraint('retries_total >= 0 AND retries_remaining >= 0', name='chk_jobs_retries_bounds'),
        sa.ForeignKeyConstraint(['project_id', 'batch_id'], ['batches.project_id', 'batches.id'], name='fk_jobs_project_batch', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id', 'cron_config_id'], ['cron_configs.project_id', 'cron_configs.id'], name='fk_jobs_project_cron_config', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id', 'queue_id'], ['queues.project_id', 'queues.id'], name='fk_jobs_project_queue', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cron_config_id', 'scheduled_for', name='uq_jobs_cron_occurrence'),
        sa.UniqueConstraint('project_id', 'id', name='uq_jobs_project_id'),
        sa.UniqueConstraint('project_id', 'idempotency_key', name='uq_jobs_idempotency')
    )
    
    # 9. job_logs (depends on jobs)
    op.create_table('job_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('length(content) <= 102400', name='chk_job_logs_length'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    
    # 10. ai_diagnostics (depends on projects, jobs)
    op.create_table('ai_diagnostics',
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('project_id', sa.String(length=36), nullable=False),
        sa.Column('diagnostic_status', sa.String(length=50), nullable=False),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('remediation_suggestion', sa.Text(), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("diagnostic_status IN ('NOT_REQUESTED', 'ANALYZING', 'COMPLETED', 'FAILED', 'UNAVAILABLE')", name='chk_ai_diagnostics_status'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id', 'job_id'], ['jobs.project_id', 'jobs.id'], name='fk_ai_diagnostics_project_job', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id')
    )

    # Add the post-alter mutually dependent foreign key constraint from batches to jobs only for non-sqlite dialects
    if op.get_context().dialect.name != 'sqlite':
        op.create_foreign_key(
            'fk_batches_callback_job',
            'batches', 'jobs',
            ['project_id', 'callback_job_id'],
            ['project_id', 'id'],
            ondelete='SET NULL'
        )

def downgrade() -> None:
    """Downgrade schema."""
    if op.get_context().dialect.name != 'sqlite':
        op.drop_constraint('fk_batches_callback_job', 'batches', type_='foreignkey')
    op.drop_table('ai_diagnostics')
    op.drop_table('job_logs')
    op.drop_table('jobs')
    op.drop_table('batches')
    op.drop_table('cron_configs')
    op.drop_table('queues')
    op.drop_table('workers')
    op.drop_table('project_members')
    op.drop_table('projects')
    op.drop_index(sa.f('ix_users_username'), table_name='users')
    op.drop_table('users')
