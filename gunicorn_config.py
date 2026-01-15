# Gunicorn Configuration
import multiprocessing

# Server configuration
bind = "0.0.0.0:5000"
workers = 2  # Reduced from 4 for stability
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "posifine"

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn.pid"

# SSL (if needed)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Application
app_name = "app:app"

# Pre-fork worker configuration
preload_app = False
max_requests = 1000
max_requests_jitter = 50

# Health checks
# Workers will be killed if they don't respond in this time
worker_int = 20
worker_abort = 30
