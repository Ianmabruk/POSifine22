#!/bin/bash
# Initialize data directory for production deployment

DATA_DIR="backend/data"

# Create data directory if it doesn't exist
mkdir -p "$DATA_DIR"

# Initialize JSON files with empty arrays if they don't exist
files=(
    "users.json"
    "products.json"
    "sales.json"
    "expenses.json"
    "batches.json"
    "discounts.json"
    "credit_requests.json"
    "settings.json"
    "reminders.json"
    "service_fees.json"
    "time_entries.json"
    "activities.json"
    "categories.json"
    "price_history.json"
    "payments.json"
    "production.json"
    "companies.json"
    "emails.json"
)

for file in "${files[@]}"; do
    if [ ! -f "$DATA_DIR/$file" ]; then
        echo "Creating $DATA_DIR/$file"
        echo "[]" > "$DATA_DIR/$file"
    fi
done

echo "✅ Data directory initialized"
