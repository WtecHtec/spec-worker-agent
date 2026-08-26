"""add_files_table

Revision ID: f7c18b93a012
Revises: e6bee304f3e2
Create Date: 2026-08-26 09:28:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c18b93a012'
down_revision: Union[str, Sequence[str], None] = 'e6bee304f3e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'files',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=True),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('mime_type', sa.String(length=100), nullable=False, server_default='application/octet-stream'),
        sa.Column('category', sa.String(length=50), nullable=False, server_default='document'),
        sa.Column('storage_type', sa.String(length=50), nullable=False, server_default='sandbox'),
        sa.Column('storage_key', sa.String(length=1000), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'file_path', name='uq_session_file_path')
    )
    op.create_index('idx_files_session_category', 'files', ['session_id', 'category'], unique=False)
    op.create_index('idx_files_session_created', 'files', ['session_id', 'created_at'], unique=False)
    op.create_index('idx_files_user_id', 'files', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_files_user_id', table_name='files')
    op.drop_index('idx_files_session_created', table_name='files')
    op.drop_index('idx_files_session_category', table_name='files')
    op.drop_table('files')
