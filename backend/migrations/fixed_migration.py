"""Add status field to UserDevice model

Revision ID: fixed_migration
Revises: 20250811_01
Create Date: 2025-08-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fixed_migration'
down_revision = '20250811_01'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Add status column as nullable first
    op.add_column('user_devices', sa.Column('status', sa.String(length=8), nullable=True))
    
    # Step 2: Add user_agent column as nullable
    op.add_column('user_devices', sa.Column('user_agent', sa.Text(), nullable=True))
    
    # Step 3: Update existing records to have status='APPROVED'
    op.execute("UPDATE user_devices SET status = 'APPROVED' WHERE status IS NULL")
    
    # Step 4: Now make the status column NOT NULL
    op.alter_column('user_devices', 'status', nullable=False)
    
    # Step 5: Add index on status
    op.create_index(op.f('ix_user_devices_status'), 'user_devices', ['status'], unique=False)


def downgrade():
    # Remove index first
    op.drop_index(op.f('ix_user_devices_status'), table_name='user_devices')
    
    # Drop the columns
    op.drop_column('user_devices', 'status')
    op.drop_column('user_devices', 'user_agent')
