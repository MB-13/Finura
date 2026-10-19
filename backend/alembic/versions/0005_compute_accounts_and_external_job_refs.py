"""compute accounts and external job refs

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08 16:13:27.922002

"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy  # noqa: F401 - used by vector columns
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql



# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('compute_accounts',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.Text(), server_default='kaggle', nullable=False),
    sa.Column('username', sa.Text(), nullable=False),
    sa.Column('ciphertext', sa.LargeBinary(), nullable=False),
    sa.Column('last4', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='unchecked', nullable=False),
    sa.Column('status_message', sa.Text(), nullable=True),
    sa.Column('gpu_used_s', sa.Integer(), nullable=True),
    sa.Column('gpu_total_s', sa.Integer(), nullable=True),
    sa.Column('quota_refresh_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_compute_accounts_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_compute_accounts')),
    sa.UniqueConstraint('user_id', 'provider', name='uq_compute_accounts_user_id_provider')
    )
    op.create_index(op.f('ix_compute_accounts_user_id'), 'compute_accounts', ['user_id'], unique=False)
    op.add_column('training_jobs', sa.Column('launch_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('training_jobs', sa.Column('external_ref', sa.Text(), nullable=True))
    op.add_column('training_jobs', sa.Column('external_url', sa.Text(), nullable=True))
    op.execute('ALTER TABLE compute_accounts ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('training_jobs', 'external_url')
    op.drop_column('training_jobs', 'external_ref')
    op.drop_column('training_jobs', 'launch_attempts')
    op.drop_index(op.f('ix_compute_accounts_user_id'), table_name='compute_accounts')
    op.drop_table('compute_accounts')
