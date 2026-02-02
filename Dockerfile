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
COPY gunicorn.conf.py ./
COPY services/ ./services/

# Create data directory
RUN mkdir -p ./data

# Set environment variables
ENV FLASK_ENV=production
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Run with Gunicorn
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
