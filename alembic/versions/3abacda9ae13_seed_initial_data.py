"""seed_initial_data

Revision ID: 3abacda9ae13
Revises: 34d490a5e9de
Create Date: 2025-11-19 21:11:16.227074

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

# revision identifiers, used by Alembic.
revision = '3abacda9ae13'
down_revision = '34d490a5e9de'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add seed data for roles and admin user"""
    
    # Define tables
    roles_table = table(
        'roles',
        column('id', UUID),
        column('name', sa.String),
        column('description', sa.String),
        column('created_at', sa.DateTime),
    )
    
    users_table = table(
        'users',
        column('id', UUID),
        column('email', sa.String),
        column('email_confirmed', sa.Boolean),
        column('password_hash', sa.String),
        column('full_name', sa.String),
        column('is_active', sa.Boolean),
        column('last_login', sa.DateTime),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime),
    )
    
    user_roles_table = table(
        'user_roles',
        column('user_id', UUID),
        column('role_id', UUID),
        column('assigned_at', sa.DateTime),
    )
    
    # Generate UUIDs
    admin_role_id = uuid.uuid4()
    tech_role_id = uuid.uuid4()
    support_role_id = uuid.uuid4()
    admin_user_id = uuid.uuid4()
    
    now = datetime.utcnow()
    
    print("\n" + "=" * 70)
    print("🌱 Seeding Initial Data")
    print("=" * 70)
    
    # Insert Roles
    print("\n📋 Inserting Roles...")
    op.bulk_insert(
        roles_table,
        [
            {
                'id': admin_role_id,
                'name': 'Admin',
                'description': 'Administrator with full system access and management capabilities',
                'created_at': now,
            },
            {
                'id': tech_role_id,
                'name': 'Tech User',
                'description': 'Technical support user with access to system configurations and integrations',
                'created_at': now,
            },
            {
                'id': support_role_id,
                'name': 'Support User',
                'description': 'Customer support user with access to tickets, chats, and customer interactions',
                'created_at': now,
            },
        ]
    )
    print("   ✅ Admin, Tech User, Support User")
    
    # Insert Default Admin User
    # Password: Admin@123456
    print("\n👤 Creating Default Admin User...")
    op.bulk_insert(
        users_table,
        [
            {
                'id': admin_user_id,
                'email': 'admin@integraserve-ai.com',
                'email_confirmed': True,
                'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYfZvJi7BLe',
                'full_name': 'System Administrator',
                'is_active': True,
                'last_login': None,
                'created_at': now,
                'updated_at': now,
            },
        ]
    )
    print("   ✅ admin@integraserve-ai.com")
    
    # Assign all roles to admin
    print("\n🔑 Assigning All Roles to Admin...")
    op.bulk_insert(
        user_roles_table,
        [
            {'user_id': admin_user_id, 'role_id': admin_role_id, 'assigned_at': now},
            {'user_id': admin_user_id, 'role_id': tech_role_id, 'assigned_at': now},
            {'user_id': admin_user_id, 'role_id': support_role_id, 'assigned_at': now},
        ]
    )
    print("   ✅ All roles assigned")
    
    print("=" * 70)
    print("✅ Seed data inserted successfully!")
    print("=" * 70)
    print("\n📧 Default Admin Credentials:")
    print("   Email: admin@integraserve-ai.com")
    print("   Password: Admin@123456")
    print("\n⚠️  IMPORTANT: Change password after first login!")
    print("=" * 70 + "\n")


def downgrade() -> None:
    """Remove seed data"""
    print("\n🗑️  Removing seed data...")
    op.execute("DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE email = 'admin@integraserve-ai.com')")
    op.execute("DELETE FROM users WHERE email = 'admin@integraserve-ai.com'")
    op.execute("DELETE FROM roles WHERE name IN ('Admin', 'Tech User', 'Support User')")
    print("✅ Seed data removed!\n")