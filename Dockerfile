# Python Flask Backend - Production Ready
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application
COPY app.py .
COPY stock_engine.py .
COPY gunicorn.conf.py .
COPY data/ ./data/

# Create data directory if it doesn't exist
RUN mkdir -p /app/data

# Set environment variables
ENV FLASK_ENV=production
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Run with Gunicorn using config file
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
