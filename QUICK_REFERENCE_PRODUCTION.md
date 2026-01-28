# 🚀 Quick Reference: Production Features

## ⚡ Testing

```bash
# Run all tests
cd backend && ./run_tests.sh

# Run specific tests
pytest tests/test_auth.py -v

# Check coverage
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

## 📊 Monitoring

```bash
# Health check
curl http://localhost:5000/health

# Sentry (requires SENTRY_DSN in .env)
# Errors automatically captured and sent to Sentry dashboard
```

## 💾 Backups

```bash
# Manual backup
python backup_database.py

# List backups
python backup_database.py --list

# Restore latest
python backup_database.py --restore latest

# Schedule daily (cron)
crontab -e
# Add: 0 2 * * * cd /path/to/backend && /path/to/python backup_database.py
```

## 🗄️ Redis Caching

```bash
# Check Redis
redis-cli ping

# Monitor cache
redis-cli MONITOR

# Clear all cache
redis-cli FLUSHDB

# Get cache stats (in Python)
from cache_manager import get_stats
print(get_stats())
```

## 🔧 Deployment

```bash
# One-command deployment
./deploy.sh

# Start production server
gunicorn -c gunicorn.conf.py app:app

# Install systemd service
sudo cp pos-backend.service /etc/systemd/system/
sudo systemctl enable pos-backend
sudo systemctl start pos-backend
```

## 📝 Environment Variables

**Required:**
```env
JWT_SECRET=your-strong-secret-key-min-32-chars
DATABASE_URL=postgresql://user:pass@host:5432/db
```

**Recommended:**
```env
REDIS_URL=redis://localhost:6379/0
SENTRY_DSN=https://xxx@sentry.io/xxx
CORS_ORIGINS=https://yourdomain.com
FLASK_ENV=production
```

## 🧪 Testing Endpoints

```bash
# Health check
curl http://localhost:5000/health

# Test authentication
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}'

# Test with rate limiting
for i in {1..10}; do 
  curl http://localhost:5000/api/auth/login
done
# Should get 429 after 5 attempts
```

## 📈 Performance

**Cache Hit Rates:**
- Products: ~75%
- Settings: ~90%
- Stats: ~85%

**Response Times:**
- Without cache: 150-300ms
- With cache: 30-80ms

## 🔍 Debugging

```bash
# Check logs
tail -f backend/app.log

# Redis cache inspection
redis-cli
> KEYS products:*
> GET products:abc123

# Test cache decorator
python -c "
from cache_manager import cached
@cached(ttl=60)
def test(): return 'cached'
print(test())
"
```

## 🚨 Common Issues

**Redis not connecting:**
```bash
# Check Redis is running
sudo systemctl status redis
# Or start it
sudo systemctl start redis
```

**Tests failing:**
```bash
# Install test deps
pip install pytest pytest-cov faker
# Run with verbose output
pytest -vv
```

**Backup fails:**
```bash
# Check pg_dump installed
which pg_dump
# Check DB connection
psql $DATABASE_URL -c "SELECT 1"
```

## 📞 Support

- **Docs**: `PRODUCTION_SETUP_GUIDE.md`
- **Analysis**: `COMPREHENSIVE_SYSTEM_ANALYSIS.md`
- **Health**: `/health` endpoint
- **Errors**: Sentry dashboard
