#!/bin/bash
set -eu

echo "🚀 Starting SAFE database initialization..."

# Am# Skip revision checks that might hang, go directly to upgrade
echo "🚀 Running flask db upgrade..."
flask db upgrade

if [ $? -eq 0 ]; then
    echo "✅ Database migration completed successfully"
else
    echo "❌ Database migration failed"
    exit 1
fiingkungan dari .env atau gunakan nilai default.
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

echo "Host Target: ${DB_HOST}, Port Target: ${DB_PORT}"

# Test database connection first
echo "🔍 Testing database connection..."
python -c "
import os
import socket
import time

max_attempts = 30
for i in range(max_attempts):
    try:
        host = os.environ.get('DB_HOST', 'db')
        port = int(os.environ.get('DB_PORT', '5432'))
        with socket.create_connection((host, port), timeout=5):
            print(f'✅ Database connection successful after {i+1} attempts')
            break
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        if i == max_attempts - 1:
            print(f'❌ Failed to connect to database after {max_attempts} attempts')
            exit(1)
        print(f'⏳ Attempt {i+1}/{max_attempts}: Database not ready, waiting...')
        time.sleep(2)
"

echo "📊 Checking current database state..."
# Check if alembic_version table exists
python -c "
import os
from sqlalchemy import create_engine, text

# Build database URL
db_user = os.environ.get('DB_USER', 'hotspot_default_user')
db_password = os.environ.get('DB_PASSWORD', 'supersecretdefaultpassword')
db_host = os.environ.get('DB_HOST', 'db')
db_name = os.environ.get('DB_NAME', 'hotspot_default_db')

db_url = f'postgresql://{db_user}:{db_password}@{db_host}:5432/{db_name}'

try:
    engine = create_engine(db_url)
    with engine.connect() as conn:
        result = conn.execute(text(\"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alembic_version')\"))
        has_alembic = result.fetchone()[0]
        
        if has_alembic:
            result = conn.execute(text('SELECT version_num FROM alembic_version'))
            current_version = result.fetchone()
            if current_version:
                print(f'📋 Current migration version: {current_version[0]}')
            else:
                print('📋 Alembic table exists but no version recorded')
        else:
            print('📋 No alembic_version table found - fresh database')
            
except Exception as e:
    print(f'⚠️ Could not check database state: {e}')
"

echo "🔄 Running database migration with safe mode..."

# Set environment variables
export FLASK_ENV=development
export FLASK_DEBUG=0

# Try to run migration with more conservative settings
echo "⏳ Attempting database upgrade..."

# Skip revision checks that might hang, go directly to upgrade
echo "� Running flask db upgrade..."
flask db upgrade

# Run the actual upgrade
echo "🚀 Running flask db upgrade..."
flask db upgrade

if [ $? -eq 0 ]; then
    echo "✅ Database migration completed successfully"
else
    echo "❌ Database migration failed"
    exit 1
fi

echo "👤 Checking for Super Admin..."
export SUPERADMIN_NAME="Kecek"
export SUPERADMIN_PHONE="0811580039"
export SUPERADMIN_ROLE="SUPER_ADMIN"
export SUPERADMIN_PASSWORD="alhabsyi"

if python -m scripts.check_superadmin; then
    echo "✅ Super Admin already exists"
else
    echo "➕ Creating Super Admin user..."
    flask user create --name "$SUPERADMIN_NAME" --phone "$SUPERADMIN_PHONE" --role "$SUPERADMIN_ROLE" --password "$SUPERADMIN_PASSWORD"
fi

echo "⚙️ Initializing default settings..."
python -m scripts.init_settings

echo "✅ Database initialization completed successfully!"

# Create completion marker
echo "Database initialization completed at $(date)" > /tmp/init_complete
echo "🎉 All initialization tasks completed!"
