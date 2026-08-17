# Use backend directory as build context
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application files from root
COPY *.py ./
COPY auth/ ./auth/
COPY services/ ./services/

# Create data directory
RUN mkdir -p ./data

# Set environment variables
ENV FLASK_ENV=production
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Run with Gunicorn
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app", "--timeout", "120", "--worker-class", "sync", "--max-requests", "1000", "--max-requests-jitter", "50", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"]
