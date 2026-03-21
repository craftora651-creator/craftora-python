"""add cj fields to users

Revision ID: 20260315_123456
Revises: 8e7991320887
Create Date: 2026-03-15 12:34:56.789012
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '20260315_123456'  # Bu otomatik gelecek
down_revision = '8e7991320887'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Users tablosuna CJ alanları ekle
    op.add_column('users', sa.Column('cj_email', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('cj_api_key', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('cj_api_secret', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('cj_connected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('cj_last_sync', sa.DateTime(timezone=True), nullable=True))
    
    # Index ekle
    op.create_index('idx_users_cj_connected', 'users', ['cj_connected_at'], unique=False)
    
    print("✅ CJ alanları users tablosuna eklendi")


def downgrade() -> None:
    # Geri alma
    op.drop_index('idx_users_cj_connected', table_name='users')
    op.drop_column('users', 'cj_last_sync')
    op.drop_column('users', 'cj_connected_at')
    op.drop_column('users', 'cj_api_secret')
    op.drop_column('users', 'cj_api_key')
    op.drop_column('users', 'cj_email')
    
    print("✅ CJ alanları users tablosundan kaldırıldı")