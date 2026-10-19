"""dataset formats

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. Existing rows are Q&A chat, which the defaults describe exactly."""
    op.add_column('style_configs', sa.Column('dataset_format', sa.Text(), server_default='qa_chat', nullable=False))
    op.add_column('dataset_pairs', sa.Column('dataset_format', sa.Text(), server_default='qa_chat', nullable=False))
    op.add_column('dataset_pairs', sa.Column('record', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('dataset_versions', sa.Column('dataset_format', sa.Text(), server_default='qa_chat', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('dataset_versions', 'dataset_format')
    op.drop_column('dataset_pairs', 'record')
    op.drop_column('dataset_pairs', 'dataset_format')
    op.drop_column('style_configs', 'dataset_format')
