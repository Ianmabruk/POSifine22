#!/bin/bash

echo "🚀 Starting Universal POS Backend..."

# Check if PostgreSQL is available
if command -v psql &> /dev/null && pg_isready -h localhost -p 5432 &> /dev/null; then
    echo "✅ PostgreSQL detected - using database backend"
    export DATABASE_URL="postgresql://localhost/pos_db"
    python app_production.py
elif [ -n "$DATABASE_URL" ]; then
    echo "✅ Database URL provided - using database backend"
    python app_production.py
else
    echo "📁 No database detected - using file-based backend"
    python app.py
fi