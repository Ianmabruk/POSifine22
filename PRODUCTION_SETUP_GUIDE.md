# 🚀 Production Setup Guide

Complete guide for deploying the Universal POS system to production with caching, monitoring, testing, and backups.

## 📋 Prerequisites

- Python 3.9+
- PostgreSQL 13+
- Redis 6+ (recommended)
- Node.js 18+ (for frontend)

## 🔧 Backend Setup

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and set the required variables:

```env
# REQUIRED
JWT_SECRET=your-strong-secret-key-min-32-chars-long
DATABASE_URL=postgresql://user:password@host:5432/database

# RECOMMENDED
REDIS_URL=redis://localhost:6379/0
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
CORS_ORIGINS=https://yourdomain.com

# OPTIONAL
BACKUP_DIR=/var/backups/pos
SMTP_HOST=smtp.gmail.com
```

### 3. Initialize Database

```bash
# Run migrations
python migrations.py

# Load initial data (optional)
python init_db.py
```

### 4. Test the Setup

```bash
# Run test suite
chmod +x run_tests.sh
./run_tests.sh

# Manual test
python smoke_test.py
```

## 📊 Monitoring Setup

### Sentry Error Tracking

1. **Create Sentry Account**: https://sentry.io
2. **Create New Project**: Choose Flask
3. **Copy DSN**: Add to `.env` file
4. **Test Integration**:

```bash
python -c "import sentry_sdk; sentry_sdk.init('YOUR_DSN'); sentry_sdk.capture_message('Test')"
```

### Health Monitoring

The backend exposes a health check endpoint:

```bash
curl http://localhost:5000/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-28T10:30:00",
  "services": {
    "database": "healthy",
    "redis": "healthy",
    "websocket": "healthy",
    "active_connections": 5
  }
}
```

**Set up monitoring**:
- **Uptime monitoring**: Pingdom, UptimeRobot, or StatusCake
- **APM**: New Relic or Datadog (optional)

## 🗄️ Redis Caching

### Install Redis

**Ubuntu/Debian:**
```bash
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

**macOS:**
```bash
brew install redis
brew services start redis
```

**Docker:**
```bash
docker run -d -p 6379:6379 redis:alpine
```

### Configure Redis

Add to `.env`:
```env
REDIS_URL=redis://localhost:6379/0
```

### Verify Redis Connection

```bash
redis-cli ping
# Should respond: PONG
```

### Cache Keys Used

- `products:{account_id}` - Product lists (5min TTL)
- `settings:{account_id}` - Account settings (10min TTL)
- `stats:{account_id}:today` - Today's statistics (2min TTL)

## 💾 Automated Backups

### Setup Backup Script

```bash
chmod +x backup_database.py
```

### Manual Backup

```bash
# Backup database
python backup_database.py

# List backups
python backup_database.py --list

# Restore from latest
python backup_database.py --restore latest
```

### Schedule Automated Backups

**Using cron (Linux/macOS):**

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd /path/to/backend && /path/to/venv/bin/python backup_database.py
```

**Using systemd timer (Linux):**

Create `/etc/systemd/system/pos-backup.service`:
```ini
[Unit]
Description=POS Database Backup

[Service]
Type=oneshot
User=your-user
WorkingDirectory=/path/to/backend
ExecStart=/path/to/venv/bin/python backup_database.py
```

Create `/etc/systemd/system/pos-backup.timer`:
```ini
[Unit]
Description=POS Backup Timer

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable timer:
```bash
sudo systemctl enable pos-backup.timer
sudo systemctl start pos-backup.timer
```

**Verify backups:**
```bash
# Check latest backups
ls -lh backend/backups/

# Test restore (CAUTION: overwrites database)
python backup_database.py --restore pos_backup_20260128_020000.sql.gz
```

## 🧪 Testing

### Run All Tests

```bash
./run_tests.sh
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest tests/test_auth.py tests/test_products.py -v

# Integration tests
pytest tests/test_api_endpoints.py -v

# With coverage
pytest --cov=. --cov-report=html
```

### Continuous Integration

**GitHub Actions** (`.github/workflows/test.yml`):

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      
      redis:
        image: redis:alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Run tests
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/test
          REDIS_URL: redis://localhost:6379/0
          JWT_SECRET: test-secret-key
        run: |
          pytest --cov=. --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## 🚦 Rate Limiting

Rate limiting is automatically enabled for authentication endpoints:

- **Login**: 5 attempts per minute per IP
- **Signup**: 3 attempts per hour per IP
- **All other endpoints**: 1000/hour, 100/minute per IP

### Configure Custom Limits

Edit `backend/app.py`:

```python
@app.route('/api/sensitive-endpoint')
@limiter.limit("10 per hour")
def sensitive_endpoint():
    pass
```

## 🔒 Security Checklist

- [ ] Strong JWT_SECRET set (min 32 characters)
- [ ] CORS restricted to your domain (not "*")
- [ ] HTTPS enabled (SSL certificate)
- [ ] Database credentials not in code
- [ ] Sentry DSN configured
- [ ] Rate limiting enabled
- [ ] Firewall configured (only ports 80, 443 open)
- [ ] Regular backups scheduled
- [ ] Error logs monitored
- [ ] Dependencies updated regularly

## 📈 Performance Optimization

### Database Indexes

Run after deployment:

```sql
-- Add performance indexes
CREATE INDEX IF NOT EXISTS idx_users_account_id ON users(account_id);
CREATE INDEX IF NOT EXISTS idx_products_account_id ON products(account_id);
CREATE INDEX IF NOT EXISTS idx_sales_account_id ON sales(account_id);
CREATE INDEX IF NOT EXISTS idx_sales_created_at ON sales(created_at);
CREATE INDEX IF NOT EXISTS idx_sales_account_date ON sales(account_id, created_at);
```

### Redis Cache Tuning

Edit `redis.conf`:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

### Application Tuning

**Gunicorn workers** (`gunicorn.conf.py`):

```python
workers = 4  # (2 * CPU cores) + 1
worker_class = 'sync'
timeout = 30
keepalive = 5
```

## 🐛 Troubleshooting

### Tests Failing

```bash
# Check dependencies
pip list | grep pytest

# Run with verbose output
pytest -vv --tb=long

# Run single test for debugging
pytest tests/test_auth.py::TestLogin::test_login_with_valid_credentials -v
```

### Redis Connection Failed

```bash
# Check Redis is running
redis-cli ping

# Check connection string
echo $REDIS_URL

# Test from Python
python -c "import redis; r=redis.from_url('redis://localhost:6379'); print(r.ping())"
```

### Sentry Not Capturing Errors

```bash
# Test Sentry integration
python -c "import sentry_sdk; sentry_sdk.init(os.environ['SENTRY_DSN']); sentry_sdk.capture_exception(Exception('Test error'))"

# Check SENTRY_DSN is set
echo $SENTRY_DSN
```

### Backup Failed

```bash
# Check pg_dump is installed
which pg_dump

# Test database connection
psql $DATABASE_URL -c "SELECT 1"

# Check backup directory permissions
ls -ld backend/backups/
```

## 📞 Support

- **Documentation**: Check `/backend/tests/` for usage examples
- **Logs**: Check Sentry dashboard for errors
- **Health**: Monitor `/health` endpoint
- **Backups**: Verify in `backend/backups/` directory

---

**Production Checklist**: Use `COMPREHENSIVE_SYSTEM_ANALYSIS.md` for complete deployment review.
