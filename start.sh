#!/bin/bash

echo "🚀 Starting POSifine Backend on Render..."

# Create data directory
mkdir -p /app/data

# Initialize data files if they don't exist
touch /app/data/users.json
touch /app/data/products.json
touch /app/data/sales.json
touch /app/data/expenses.json
touch /app/data/discounts.json
touch /app/data/credit_requests.json
touch /app/data/reminders.json
touch /app/data/settings.json
touch /app/data/batches.json

# Initialize with empty arrays/objects if needed
for file in users products sales expenses discounts credit_requests reminders batches; do
    if [ ! -s /app/data/${file}.json ] || ! grep -q "^\[" /app/data/${file}.json; then
        echo '[]' > /app/data/${file}.json
    fi
done

# Settings file needs to be an object
if [ ! -s /app/data/settings.json ] || ! grep -q "^{" /app/data/settings.json; then
    echo '{}' > /app/data/settings.json
fi

# Get PORT from environment or default to 5000
PORT=${PORT:-5000}

echo "✅ Data files initialized"
echo "📦 Starting Gunicorn on port $PORT..."

# Start with Gunicorn
exec gunicorn -w 4 -b 0.0.0.0:$PORT app:app --timeout 120 --access-logfile - --error-logfile -