"""projects documents chunks

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-07 14:58:23.105388

"""
from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

PROJECT_STATUSES = ('draft', 'uploaded', 'parsing', 'awaiting_style', 'previewing', 'generating', 'in_review',
                    'awaiting_run', 'training', 'paused', 'evaluating', 'ready', 'failed')
DOCUMENT_STATUSES = ('pending_upload', 'uploaded', 'parsing', 'parsed', 'failed')
project_status = postgresql.ENUM(*PROJECT_STATUSES, name='project_status', create_type=False)
document_status = postgresql.ENUM(*DOCUMENT_STATUSES, name='document_status', create_type=False)

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    project_status.create(op.get_bind(), checkfirst=True)
    document_status.create(op.get_bind(), checkfirst=True)
    op.create_table('projects',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('status', project_status, server_default='draft', nullable=False),
    sa.Column('status_reason', sa.Text(), nullable=True),
    sa.Column('status_message', sa.Text(), nullable=True),
    sa.Column('status_retry_to', project_status, nullable=True),
    sa.Column('status_changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('base_model_id', sa.Text(), nullable=True),
    sa.Column('base_model_license', sa.Text(), nullable=True),
    sa.Column('base_model_is_custom', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('license_ack_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('gen_provider', sa.Text(), nullable=True),
    sa.Column('gen_model', sa.Text(), nullable=True),
    sa.Column('style_id', sa.UUID(), nullable=True),
    sa.Column('total_bytes', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('target_pairs', sa.Integer(), server_default='500', nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_projects_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    op.create_index('ix_projects_user_id_updated_at', 'projects', ['user_id', 'updated_at'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('content_type', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('sha256', sa.Text(), nullable=True),
    sa.Column('status', document_status, server_default='pending_upload', nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('ocr_pages', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_documents_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents')),
    sa.UniqueConstraint('storage_key', name=op.f('uq_documents_storage_key'))
    )
    op.create_index(op.f('ix_documents_project_id'), 'documents', ['project_id'], unique=False)
    op.create_table('project_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('from_status', project_status, nullable=True),
    sa.Column('to_status', project_status, nullable=True),
    sa.Column('actor', sa.Text(), nullable=False),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_events_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_events'))
    )
    op.create_index('ix_project_events_project_id_at', 'project_events', ['project_id', 'at'], unique=False)
    op.create_table('chunks',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('section_path', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('page_start', sa.Integer(), nullable=True),
    sa.Column('page_end', sa.Integer(), nullable=True),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_chunks_document_id_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_chunks_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chunks')),
    sa.UniqueConstraint('document_id', 'ordinal', name='uq_chunks_document_id_ordinal')
    )
    op.create_index(op.f('ix_chunks_document_id'), 'chunks', ['document_id'], unique=False)
    op.create_index(op.f('ix_chunks_project_id'), 'chunks', ['project_id'], unique=False)
    for table in ('projects', 'project_events', 'documents', 'chunks'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_chunks_project_id'), table_name='chunks')
    op.drop_index(op.f('ix_chunks_document_id'), table_name='chunks')
    op.drop_table('chunks')
    op.drop_index('ix_project_events_project_id_at', table_name='project_events')
    op.drop_table('project_events')
    op.drop_index(op.f('ix_documents_project_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index('ix_projects_user_id_updated_at', table_name='projects')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_table('projects')
    document_status.drop(op.get_bind(), checkfirst=True)
    project_status.drop(op.get_bind(), checkfirst=True)
