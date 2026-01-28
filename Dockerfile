# Use backend directory as build context
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy backend files
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy all backend application files
COPY backend/*.py ./
COPY backend/gunicorn.conf.py ./
COPY backend/data/ ./data/ 2>/dev/null || mkdir -p ./data

# Set environment variables
ENV FLASK_ENV=production
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Run with Gunicorn
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
