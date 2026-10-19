"""keys style generation dataset

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-07 15:32:54.559681

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 - used by vector columns
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

provider_enum = postgresql.ENUM('groq', 'gemini', 'cerebras', name='provider', create_type=False)
key_status_enum = postgresql.ENUM('unverified', 'valid', 'invalid', 'quota_exhausted', name='key_status', create_type=False)
gen_kind_enum = postgresql.ENUM('preview', 'full', name='gen_kind', create_type=False)
gen_state_enum = postgresql.ENUM('queued', 'running', 'waiting_quota', 'finalizing', 'done', 'failed', 'cancelled', name='gen_state', create_type=False)
pair_origin_enum = postgresql.ENUM('generated', 'user_added', name='pair_origin', create_type=False)
pair_split_enum = postgresql.ENUM('unassigned', 'train', 'eval', name='pair_split', create_type=False)
unit_state_enum = postgresql.ENUM('pending', 'queued', 'done', 'failed', 'cancelled', name='unit_state', create_type=False)

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    provider_enum.create(op.get_bind(), checkfirst=True)
    key_status_enum.create(op.get_bind(), checkfirst=True)
    gen_kind_enum.create(op.get_bind(), checkfirst=True)
    gen_state_enum.create(op.get_bind(), checkfirst=True)
    pair_origin_enum.create(op.get_bind(), checkfirst=True)
    pair_split_enum.create(op.get_bind(), checkfirst=True)
    unit_state_enum.create(op.get_bind(), checkfirst=True)
    op.create_table('provider_keys',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('provider', provider_enum, nullable=False),
    sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
    sa.Column('last4', sa.Text(), nullable=False),
    sa.Column('status', key_status_enum, server_default='unverified', nullable=False),
    sa.Column('priority', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('default_model', sa.Text(), nullable=True),
    sa.Column('terms_acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('quota_reset_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_provider_keys_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_provider_keys')),
    sa.UniqueConstraint('user_id', 'provider', name='uq_provider_keys_user_id_provider')
    )
    op.create_index(op.f('ix_provider_keys_user_id'), 'provider_keys', ['user_id'], unique=False)
    op.create_table('dataset_versions',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('train_count', sa.Integer(), nullable=False),
    sa.Column('eval_count', sa.Integer(), nullable=False),
    sa.Column('train_key', sa.Text(), nullable=False),
    sa.Column('eval_key', sa.Text(), nullable=False),
    sa.Column('sha256_train', sa.Text(), nullable=False),
    sa.Column('sha256_eval', sa.Text(), nullable=False),
    sa.Column('system_prompt', sa.Text(), nullable=True),
    sa.Column('stats', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_dataset_versions_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset_versions')),
    sa.UniqueConstraint('project_id', 'version', name='uq_dataset_versions_project_id_version')
    )
    op.create_index(op.f('ix_dataset_versions_project_id'), 'dataset_versions', ['project_id'], unique=False)
    op.create_table('style_configs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('template_key', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('tone', sa.Text(), nullable=False),
    sa.Column('length', sa.Text(), nullable=False),
    sa.Column('format', sa.Text(), nullable=False),
    sa.Column('language', sa.Text(), nullable=False),
    sa.Column('examples', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('system_prompt_in_data', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('content_hash', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_style_configs_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_style_configs'))
    )
    op.create_index(op.f('ix_style_configs_content_hash'), 'style_configs', ['content_hash'], unique=False)
    op.create_index(op.f('ix_style_configs_project_id'), 'style_configs', ['project_id'], unique=False)
    op.create_table('generation_runs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('style_id', sa.UUID(), nullable=False),
    sa.Column('kind', gen_kind_enum, nullable=False),
    sa.Column('state', gen_state_enum, nullable=False),
    sa.Column('prompt_version', sa.Text(), nullable=False),
    sa.Column('pairs_per_chunk', sa.SmallInteger(), nullable=False),
    sa.Column('target_pairs', sa.Integer(), nullable=False),
    sa.Column('provider_chain', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('total_chunks', sa.Integer(), server_default='0', nullable=False),
    sa.Column('done_chunks', sa.Integer(), server_default='0', nullable=False),
    sa.Column('pairs_generated', sa.Integer(), server_default='0', nullable=False),
    sa.Column('pairs_kept', sa.Integer(), server_default='0', nullable=False),
    sa.Column('tokens_in', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('tokens_out', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('resume_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_generation_runs_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['style_id'], ['style_configs.id'], name=op.f('fk_generation_runs_style_id_style_configs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_generation_runs'))
    )
    op.create_index(op.f('ix_generation_runs_project_id'), 'generation_runs', ['project_id'], unique=False)
    op.create_table('dataset_pairs',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=True),
    sa.Column('chunk_id', sa.UUID(), nullable=True),
    sa.Column('origin', pair_origin_enum, nullable=False),
    sa.Column('preview', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('judge_correctness', sa.SmallInteger(), nullable=True),
    sa.Column('judge_style', sa.SmallInteger(), nullable=True),
    sa.Column('judge_reason', sa.Text(), nullable=True),
    sa.Column('kept', sa.Boolean(), nullable=True),
    sa.Column('dropped_reason', sa.Text(), nullable=True),
    sa.Column('duplicate_of', sa.UUID(), nullable=True),
    sa.Column('split', pair_split_enum, server_default='unassigned', nullable=False),
    sa.Column('edited', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id'], name=op.f('fk_dataset_pairs_chunk_id_chunks'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_dataset_pairs_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['generation_runs.id'], name=op.f('fk_dataset_pairs_run_id_generation_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dataset_pairs'))
    )
    op.create_index('ix_dataset_pairs_project_split_kept', 'dataset_pairs', ['project_id', 'split', 'kept'], unique=False)
    op.create_index(op.f('ix_dataset_pairs_run_id'), 'dataset_pairs', ['run_id'], unique=False)
    op.create_table('generation_units',
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('chunk_id', sa.UUID(), nullable=False),
    sa.Column('state', unit_state_enum, nullable=False),
    sa.Column('generated', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('judged', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('attempts', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['chunk_id'], ['chunks.id'], name=op.f('fk_generation_units_chunk_id_chunks'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['generation_runs.id'], name=op.f('fk_generation_units_run_id_generation_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('run_id', 'chunk_id', name=op.f('pk_generation_units'))
    )
    op.add_column('projects', sa.Column('dataset_version_id', sa.UUID(), nullable=True))
    op.execute('ALTER TABLE provider_keys ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE dataset_versions ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE style_configs ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE generation_runs ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE dataset_pairs ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE generation_units ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('projects', 'dataset_version_id')
    op.drop_table('generation_units')
    op.drop_index(op.f('ix_dataset_pairs_run_id'), table_name='dataset_pairs')
    op.drop_index('ix_dataset_pairs_project_split_kept', table_name='dataset_pairs')
    op.drop_table('dataset_pairs')
    op.drop_index(op.f('ix_generation_runs_project_id'), table_name='generation_runs')
    op.drop_table('generation_runs')
    op.drop_index(op.f('ix_style_configs_project_id'), table_name='style_configs')
    op.drop_index(op.f('ix_style_configs_content_hash'), table_name='style_configs')
    op.drop_table('style_configs')
    op.drop_index(op.f('ix_dataset_versions_project_id'), table_name='dataset_versions')
    op.drop_table('dataset_versions')
    op.drop_index(op.f('ix_provider_keys_user_id'), table_name='provider_keys')
    op.drop_table('provider_keys')
    provider_enum.drop(op.get_bind(), checkfirst=True)
    key_status_enum.drop(op.get_bind(), checkfirst=True)
    gen_kind_enum.drop(op.get_bind(), checkfirst=True)
    gen_state_enum.drop(op.get_bind(), checkfirst=True)
    pair_origin_enum.drop(op.get_bind(), checkfirst=True)
    pair_split_enum.drop(op.get_bind(), checkfirst=True)
    unit_state_enum.drop(op.get_bind(), checkfirst=True)
