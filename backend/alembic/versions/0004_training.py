"""training

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-07 15:45:35.079832

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 - used by vector columns
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

job_state_enum = postgresql.ENUM('created', 'running', 'paused', 'evaluating', 'completed', 'cancelled', 'failed', name='job_state', create_type=False)
pause_reason_enum = postgresql.ENUM('session_ended', 'idle_timeout', 'no_gpu', 'stopped', 'heartbeat_timeout', 'user_stopped', name='pause_reason', create_type=False)
artifact_kind_enum = postgresql.ENUM('adapter_safetensors', 'adapter_gguf', 'checkpoint_gguf', 'eval_generations', name='artifact_kind', create_type=False)
eval_state_enum = postgresql.ENUM('pending', 'scoring', 'done', 'failed', name='eval_state', create_type=False)

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    job_state_enum.create(op.get_bind(), checkfirst=True)
    pause_reason_enum.create(op.get_bind(), checkfirst=True)
    artifact_kind_enum.create(op.get_bind(), checkfirst=True)
    eval_state_enum.create(op.get_bind(), checkfirst=True)
    op.create_table('training_jobs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('dataset_version_id', sa.UUID(), nullable=False),
    sa.Column('backend', sa.Text(), nullable=False),
    sa.Column('base_model_id', sa.Text(), nullable=False),
    sa.Column('base_model_license', sa.Text(), nullable=True),
    sa.Column('is_llama', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('train_mode', sa.Text(), nullable=False),
    sa.Column('preset', sa.Text(), nullable=False),
    sa.Column('hyperparams', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('lib_versions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('notebook_version', sa.Text(), nullable=False),
    sa.Column('state', job_state_enum, nullable=False),
    sa.Column('current_step', sa.Integer(), server_default='0', nullable=False),
    sa.Column('max_steps', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_loss', sa.Float(), nullable=True),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('pause_reason', pause_reason_enum, nullable=True),
    sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('runtime_info', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('exports', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'], name=op.f('fk_training_jobs_dataset_version_id_dataset_versions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_training_jobs_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_training_jobs'))
    )
    op.create_index(op.f('ix_training_jobs_project_id'), 'training_jobs', ['project_id'], unique=False)
    op.create_index(op.f('ix_training_jobs_state'), 'training_jobs', ['state'], unique=False)
    op.create_table('artifacts',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('kind', artifact_kind_enum, nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.Text(), nullable=True),
    sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('uploaded', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['training_jobs.id'], name=op.f('fk_artifacts_job_id_training_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artifacts'))
    )
    op.create_index(op.f('ix_artifacts_job_id'), 'artifacts', ['job_id'], unique=False)
    op.create_table('checkpoints',
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('step', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.Text(), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['training_jobs.id'], name=op.f('fk_checkpoints_job_id_training_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('job_id', name=op.f('pk_checkpoints'))
    )
    op.create_table('evaluations',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('state', eval_state_enum, nullable=False),
    sa.Column('n_items', sa.Integer(), nullable=False),
    sa.Column('base_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('tuned_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('samples', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['training_jobs.id'], name=op.f('fk_evaluations_job_id_training_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_evaluations')),
    sa.UniqueConstraint('job_id', name=op.f('uq_evaluations_job_id'))
    )
    op.create_table('job_tokens',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('token_prefix', sa.Text(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['training_jobs.id'], name=op.f('fk_job_tokens_job_id_training_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_job_tokens_token_hash'))
    )
    op.create_index(op.f('ix_job_tokens_job_id'), 'job_tokens', ['job_id'], unique=False)
    op.create_table('training_metrics',
    sa.Column('job_id', sa.UUID(), nullable=False),
    sa.Column('step', sa.Integer(), nullable=False),
    sa.Column('loss', sa.Float(), nullable=True),
    sa.Column('lr', sa.Float(), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_id'], ['training_jobs.id'], name=op.f('fk_training_metrics_job_id_training_jobs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('job_id', 'step', name=op.f('pk_training_metrics'))
    )
    op.execute('ALTER TABLE training_jobs ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE checkpoints ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE evaluations ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE job_tokens ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE training_metrics ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('training_metrics')
    op.drop_index(op.f('ix_job_tokens_job_id'), table_name='job_tokens')
    op.drop_table('job_tokens')
    op.drop_table('evaluations')
    op.drop_table('checkpoints')
    op.drop_index(op.f('ix_artifacts_job_id'), table_name='artifacts')
    op.drop_table('artifacts')
    op.drop_index(op.f('ix_training_jobs_state'), table_name='training_jobs')
    op.drop_index(op.f('ix_training_jobs_project_id'), table_name='training_jobs')
    op.drop_table('training_jobs')
    job_state_enum.drop(op.get_bind(), checkfirst=True)
    pause_reason_enum.drop(op.get_bind(), checkfirst=True)
    artifact_kind_enum.drop(op.get_bind(), checkfirst=True)
    eval_state_enum.drop(op.get_bind(), checkfirst=True)
