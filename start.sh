#!/bin/bash
set -e

echo "🚀 Starting POSifine Backend..."

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
DATA_DIR="${SCRIPT_DIR}/data"

# Change to script directory to ensure app.py is found
cd "$SCRIPT_DIR"

# Detect Python command - use venv if available
VENV_PYTHON="${PARENT_DIR}/.venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    PYTHON_CMD="$VENV_PYTHON"
    echo "✅ Using virtual environment Python"
else
    PYTHON_CMD="python3"
    echo "⚠️ Using system Python (venv not found)"
fi

# Verify syntax
echo "✅ Verifying app syntax..."
$PYTHON_CMD -m py_compile app.py

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
exec $PYTHON_CMD -m gunicorn -w 2 -b 0.0.0.0:$PORT app:app \
    --timeout 120 \
    --worker-class sync \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
