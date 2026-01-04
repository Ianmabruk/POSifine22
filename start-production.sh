#!/bin/bash

# Production deployment script for POS Backend

echo "🚀 Starting POS Backend Production Deployment..."

# Set production environment
export FLASK_ENV=production
export PORT=${PORT:-5002}

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Create data directory if it doesn't exist
mkdir -p data

# Start the application
echo "🔥 Starting POS Backend on port $PORT..."
python app.py