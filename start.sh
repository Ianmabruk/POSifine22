#!/bin/bash
set -e

echo "🚀 Starting POSifine Backend..."

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
DATA_DIR="${SCRIPT_DIR}/data"

# Kill any existing process on port 5000
if lsof -Pi :5000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  Port 5000 in use. Killing old process..."
    lsof -ti:5000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Verify syntax
echo "✅ Verifying app syntax..."
python3 -m py_compile app.py

# Test import
echo "✅ Testing app import..."
python3 -c "from app import app; print('✅ App imports OK')" 2>&1

# Create data directory
mkdir -p "${DATA_DIR}"

# Initialize data files if they don't exist
touch "${DATA_DIR}/users.json"
touch "${DATA_DIR}/products.json"
touch "${DATA_DIR}/sales.json"
touch "${DATA_DIR}/expenses.json"
touch "${DATA_DIR}/discounts.json"
touch "${DATA_DIR}/credit_requests.json"
touch "${DATA_DIR}/reminders.json"
touch "${DATA_DIR}/settings.json"
touch "${DATA_DIR}/batches.json"

# Initialize with empty arrays/objects if needed
for file in users products sales expenses discounts credit_requests reminders batches; do
    if [ ! -s "${DATA_DIR}/${file}.json" ] || ! grep -q "^\[" "${DATA_DIR}/${file}.json"; then
        echo '[]' > "${DATA_DIR}/${file}.json"
    fi
done

# Settings file needs to be an object
if [ ! -s "${DATA_DIR}/settings.json" ] || ! grep -q "^{" "${DATA_DIR}/settings.json"; then
    echo '{}' > "${DATA_DIR}/settings.json"
fi

# Get PORT from environment or default to 5000
PORT=${PORT:-5000}

echo "✅ Data files initialized"
echo "📦 Starting Gunicorn on port $PORT with 2 workers..."

# Start with Gunicorn (reduced workers for stability)
exec gunicorn -w 2 -b 0.0.0.0:$PORT app:app \
    --timeout 120 \
    --worker-class sync \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile - \
    --log-level info