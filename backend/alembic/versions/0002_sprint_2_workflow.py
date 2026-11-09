"""sprint 2 workflow

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27 01:29:50.246370
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2  # noqa: F401
from sqlalchemy.dialects import postgresql


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('password_reset_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_password_reset_tokens_user_id'), 'password_reset_tokens', ['user_id'], unique=False)
    op.create_table('site_baselines',
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('target_year', sa.Integer(), nullable=False),
    sa.Column('n_obs', sa.Integer(), nullable=False),
    sa.Column('median_ndvi', sa.Float(), nullable=True),
    sa.Column('robust_sd', sa.Float(), nullable=True),
    sa.Column('p10', sa.Float(), nullable=True),
    sa.Column('p90', sa.Float(), nullable=True),
    sa.Column('years', sa.String(length=64), nullable=False),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('site_id', 'month')
    )
    op.create_table('signals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('open', 'under_inspection', 'dismissed', 'closed', name='signal_status'), nullable=False),
    sa.Column('outcome', sa.Enum('confirmed', 'not_confirmed', 'inconclusive', name='signal_outcome'), nullable=True),
    sa.Column('outcome_method', sa.String(length=32), nullable=True),
    sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reopened_count', sa.Integer(), nullable=False),
    sa.Column('first_obs_on', sa.Date(), nullable=False),
    sa.Column('last_obs_on', sa.Date(), nullable=False),
    sa.Column('latest_ndvi', sa.Float(), nullable=False),
    sa.Column('baseline_median', sa.Float(), nullable=False),
    sa.Column('baseline_sd', sa.Float(), nullable=False),
    sa.Column('deviation', sa.Float(), nullable=False),
    sa.Column('z_score', sa.Float(), nullable=False),
    sa.Column('priority_score', sa.Float(), nullable=False),
    sa.Column('priority_factors', sa.JSON(), nullable=False),
    sa.Column('evidence', sa.JSON(), nullable=False),
    sa.Column('before_obs_id', sa.Uuid(), nullable=True),
    sa.Column('after_obs_id', sa.Uuid(), nullable=True),
    sa.Column('before_image', sa.String(length=80), nullable=True),
    sa.Column('after_image', sa.String(length=80), nullable=True),
    sa.ForeignKeyConstraint(['after_obs_id'], ['observations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['before_obs_id'], ['observations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_signals_site_id'), 'signals', ['site_id'], unique=False)
    op.create_index(op.f('ix_signals_status'), 'signals', ['status'], unique=False)
    op.create_index('uq_signals_one_active_per_site', 'signals', ['site_id'], unique=True, postgresql_where=sa.text("status IN ('open', 'under_inspection')"))
    op.create_table('signal_decisions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('signal_id', sa.Uuid(), nullable=False),
    sa.Column('decision', sa.Enum('dismiss', 'confirm', 'send_for_inspection', 'inspection_cancelled', 'record_outcome', 'reopened', name='decision_type'), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    # signal_outcome was created with the signals table above; reuse it.
    sa.Column('outcome', postgresql.ENUM('confirmed', 'not_confirmed', 'inconclusive', name='signal_outcome', create_type=False), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_signal_decisions_signal_id'), 'signal_decisions', ['signal_id'], unique=False)
    op.create_table('tasks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('signal_id', sa.Uuid(), nullable=True),
    sa.Column('task_type', sa.Enum('inspection', 'maintenance', name='task_type'), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('instructions', sa.Text(), nullable=True),
    sa.Column('priority', sa.Enum('high', 'medium', 'low', name='task_priority'), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=False),
    sa.Column('assignee_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('assigned', 'in_progress', 'completed', 'cancelled', name='task_status'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tasks_assignee_id'), 'tasks', ['assignee_id'], unique=False)
    op.create_index(op.f('ix_tasks_signal_id'), 'tasks', ['signal_id'], unique=False)
    op.create_index(op.f('ix_tasks_site_id'), 'tasks', ['site_id'], unique=False)
    op.create_index(op.f('ix_tasks_status'), 'tasks', ['status'], unique=False)
    op.create_table('task_findings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('task_id', sa.Uuid(), nullable=False),
    sa.Column('visit_date', sa.Date(), nullable=True),
    sa.Column('condition', sa.Enum('healthy', 'stressed', 'damaged', 'dead_or_missing', 'not_vegetation', name='observed_condition'), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('recorded_by', sa.Uuid(), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['recorded_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id')
    )
    op.create_table('finding_photos',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('finding_id', sa.Uuid(), nullable=False),
    sa.Column('file_name', sa.String(length=80), nullable=False),
    sa.Column('thumb_name', sa.String(length=80), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('uploaded_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['finding_id'], ['task_findings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_finding_photos_finding_id'), 'finding_photos', ['finding_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_finding_photos_finding_id'), table_name='finding_photos')
    op.drop_table('finding_photos')
    op.drop_table('task_findings')
    op.drop_index(op.f('ix_tasks_status'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_site_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_signal_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_assignee_id'), table_name='tasks')
    op.drop_table('tasks')
    op.drop_index(op.f('ix_signal_decisions_signal_id'), table_name='signal_decisions')
    op.drop_table('signal_decisions')
    op.drop_index('uq_signals_one_active_per_site', table_name='signals', postgresql_where=sa.text("status IN ('open', 'under_inspection')"))
    op.drop_index(op.f('ix_signals_status'), table_name='signals')
    op.drop_index(op.f('ix_signals_site_id'), table_name='signals')
    op.drop_table('signals')
    op.drop_table('site_baselines')
    op.drop_index(op.f('ix_password_reset_tokens_user_id'), table_name='password_reset_tokens')
    op.drop_table('password_reset_tokens')
    for name in ('observed_condition', 'task_status', 'task_priority', 'task_type', 'decision_type',
                 'signal_outcome', 'signal_status'):
        op.execute(f'DROP TYPE IF EXISTS {name}')
