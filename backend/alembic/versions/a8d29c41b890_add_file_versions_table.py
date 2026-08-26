"""add_file_versions_table

Revision ID: a8d29c41b890
Revises: f7c18b93a012
Create Date: 2026-08-26 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d29c41b890'
down_revision: Union[str, Sequence[str], None] = 'f7c18b93a012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'file_versions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('file_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=True),
        sa.Column('version_num', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('file_size', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('diff_content', sa.Text(), nullable=True),
        sa.Column('storage_key', sa.String(length=1000), nullable=True),
        sa.Column('summary', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('file_id', 'version_num', name='uq_file_version_num')
    )
    op.create_index('idx_file_versions_file_id', 'file_versions', ['file_id'], unique=False)
    op.create_index('idx_file_versions_session_id', 'file_versions', ['session_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_file_versions_session_id', table_name='file_versions')
    op.drop_index('idx_file_versions_file_id', table_name='file_versions')
    op.drop_table('file_versions')
