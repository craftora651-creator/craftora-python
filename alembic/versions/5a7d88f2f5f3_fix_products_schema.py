"""fix_user_model_only

Revision ID: 8e7991320887
Revises: 
Create Date: 2026-01-30 17:52:22.993813
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '8e7991320887'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column('users', 'metadata', new_column_name='user_metadata',
                   existing_type=postgresql.JSONB())
    op.add_column('users', sa.Column('seller_verified', sa.Boolean(), 
                  server_default=sa.false()))
    op.add_column('users', sa.Column('verified_at', sa.DateTime(timezone=True)))
    op.add_column('users', sa.Column('phone_number', sa.String(20)))
    op.add_column('users', sa.Column('tax_id', sa.String(50)))
    op.add_column('users', sa.Column('business_name', sa.String(255)))
    op.create_index('idx_users_seller_verification', 'users', 
                   ['role', 'seller_verified', 'is_active'])
    op.create_index('idx_users_last_login', 'users', ['last_login_at'])
    op.create_check_constraint('chk_phone_format', 'users',
        "phone_number IS NULL OR phone_number ~ '^\\+?[0-9\\s\\-\\(\\)]{10,20}$'")

def downgrade() -> None:
    # 1. Index'leri sil
    op.drop_index('idx_products_shop_id', table_name='products')
    op.drop_index('idx_products_slug', table_name='products')
    op.drop_index('idx_products_status', table_name='products')
    op.drop_index('idx_products_product_type', table_name='products')
    
    # 2. Foreign key'i geri ekle
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'product_variants'
            ) THEN
                ALTER TABLE cart_items 
                ADD CONSTRAINT cart_items_variant_id_fkey 
                FOREIGN KEY (variant_id) REFERENCES product_variants(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)