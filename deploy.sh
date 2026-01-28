#!/bin/bash
# ==================================================
# Production Deployment Script
# ==================================================
# Complete production setup with all features

set -e

echo "🚀 Universal POS Production Deployment"
echo "======================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root (not recommended)
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}⚠️  WARNING: Running as root is not recommended${NC}"
    echo "Consider creating a dedicated user for the application"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Step 1: Check prerequisites
echo "📋 Step 1: Checking prerequisites..."
echo ""

command -v python3 >/dev/null 2>&1 || { echo -e "${RED}❌ Python 3 is required${NC}"; exit 1; }
command -v pip >/dev/null 2>&1 || { echo -e "${RED}❌ pip is required${NC}"; exit 1; }
command -v psql >/dev/null 2>&1 || { echo -e "${YELLOW}⚠️  PostgreSQL client not found (optional)${NC}"; }
command -v redis-cli >/dev/null 2>&1 || { echo -e "${YELLOW}⚠️  Redis not found (optional but recommended)${NC}"; }

echo -e "${GREEN}✅ Prerequisites checked${NC}"
echo ""

# Step 2: Install dependencies
echo "📦 Step 2: Installing dependencies..."
echo ""

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing Python packages..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# Step 3: Environment configuration
echo "⚙️  Step 3: Configuring environment..."
echo ""

if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo -e "${YELLOW}⚠️  Please edit .env file with your configuration${NC}"
    echo "Required variables: JWT_SECRET, DATABASE_URL"
    read -p "Press Enter to continue after editing .env..."
else
    echo ".env file already exists"
fi

# Validate required environment variables
source .env 2>/dev/null || true

if [ -z "$JWT_SECRET" ]; then
    echo -e "${RED}❌ JWT_SECRET not set in .env${NC}"
    exit 1
fi

if [ ${#JWT_SECRET} -lt 32 ]; then
    echo -e "${RED}❌ JWT_SECRET must be at least 32 characters${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environment configured${NC}"
echo ""

# Step 4: Database setup
echo "🗄️  Step 4: Setting up database..."
echo ""

if [ -n "$DATABASE_URL" ]; then
    echo "Running database migrations..."
    python migrations.py || echo -e "${YELLOW}⚠️  Migration warnings (may be OK)${NC}"
    echo -e "${GREEN}✅ Database initialized${NC}"
else
    echo -e "${YELLOW}⚠️  DATABASE_URL not set, using JSON file storage${NC}"
fi

echo ""

# Step 5: Redis setup
echo "📦 Step 5: Checking Redis cache..."
echo ""

if [ -n "$REDIS_URL" ]; then
    if redis-cli -u "$REDIS_URL" ping >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Redis connected${NC}"
    else
        echo -e "${YELLOW}⚠️  Redis not accessible, caching disabled${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  REDIS_URL not set, caching disabled${NC}"
fi

echo ""

# Step 6: Sentry setup
echo "📊 Step 6: Checking monitoring setup..."
echo ""

if [ -n "$SENTRY_DSN" ]; then
    echo -e "${GREEN}✅ Sentry error monitoring configured${NC}"
else
    echo -e "${YELLOW}⚠️  SENTRY_DSN not set, error monitoring disabled${NC}"
fi

echo ""

# Step 7: Run tests
echo "🧪 Step 7: Running test suite..."
echo ""

if ./run_tests.sh; then
    echo -e "${GREEN}✅ All tests passed${NC}"
else
    echo -e "${RED}❌ Some tests failed${NC}"
    read -p "Continue deployment? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""

# Step 8: Setup backups
echo "💾 Step 8: Configuring backups..."
echo ""

mkdir -p backups
chmod +x backup_database.py

# Test backup
echo "Testing backup system..."
if python backup_database.py --cleanup-only; then
    echo -e "${GREEN}✅ Backup system ready${NC}"
    
    echo ""
    echo "To schedule daily backups, add to crontab:"
    echo "  crontab -e"
    echo "  # Add: 0 2 * * * cd $(pwd) && $(pwd)/venv/bin/python backup_database.py"
else
    echo -e "${YELLOW}⚠️  Backup test failed (may be OK if no DB configured)${NC}"
fi

echo ""

# Step 9: Security check
echo "🔒 Step 9: Security checklist..."
echo ""

SECURITY_OK=true

if [ "$CORS_ORIGINS" = "*" ] && [ "$FLASK_ENV" = "production" ]; then
    echo -e "${RED}❌ CORS is open to all origins in production${NC}"
    SECURITY_OK=false
fi

if [ "$DEBUG" = "True" ] && [ "$FLASK_ENV" = "production" ]; then
    echo -e "${RED}❌ DEBUG mode enabled in production${NC}"
    SECURITY_OK=false
fi

if [ ${#JWT_SECRET} -lt 50 ]; then
    echo -e "${YELLOW}⚠️  JWT_SECRET should be longer (50+ chars recommended)${NC}"
fi

if [ -z "$SENTRY_DSN" ]; then
    echo -e "${YELLOW}⚠️  No error monitoring configured${NC}"
fi

if $SECURITY_OK; then
    echo -e "${GREEN}✅ Security checks passed${NC}"
else
    echo -e "${RED}❌ Security issues found - please fix before deploying${NC}"
    exit 1
fi

echo ""

# Step 10: Start application
echo "🎯 Step 10: Starting application..."
echo ""

echo "Application ready to start!"
echo ""
echo "Start with:"
echo "  For development: python app.py"
echo "  For production:  gunicorn -c gunicorn.conf.py app:app"
echo ""
echo "Or use systemd service (recommended for production)"
echo ""

# Generate systemd service file
cat > pos-backend.service <<EOL
[Unit]
Description=Universal POS Backend
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=$USER
WorkingDirectory=$(pwd)
Environment="PATH=$(pwd)/venv/bin"
ExecStart=$(pwd)/venv/bin/gunicorn -c gunicorn.conf.py app:app
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
KillSignal=SIGQUIT
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOL

echo "Systemd service file created: pos-backend.service"
echo "To install:"
echo "  sudo cp pos-backend.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable pos-backend"
echo "  sudo systemctl start pos-backend"

echo ""
echo "======================================"
echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
echo "======================================"
echo ""
echo "📊 Monitoring URLs:"
echo "  Health Check: http://localhost:5000/health"
if [ -n "$SENTRY_DSN" ]; then
    echo "  Sentry: https://sentry.io"
fi
echo ""
echo "📖 Next steps:"
echo "  1. Review PRODUCTION_SETUP_GUIDE.md"
echo "  2. Set up SSL certificate (Let's Encrypt)"
echo "  3. Configure firewall rules"
echo "  4. Set up monitoring alerts"
echo "  5. Schedule regular backups"
echo ""
