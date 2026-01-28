#!/bin/bash

# Frontend Deployment Script for Netlify
# Automates the build process with proper checks

set -e  # Exit on error

echo "=================================="
echo "🚀 Frontend Deployment Script"
echo "=================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "my-react-app/package.json" ]; then
    echo -e "${RED}❌ Error: my-react-app/package.json not found${NC}"
    echo "Please run this script from the project root directory"
    exit 1
fi

echo -e "${BLUE}📁 Navigating to frontend directory...${NC}"
cd my-react-app

# Check Node version
echo -e "${BLUE}🔍 Checking Node version...${NC}"
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}❌ Node version must be 18 or higher${NC}"
    echo "Current version: $(node -v)"
    exit 1
fi
echo -e "${GREEN}✅ Node $(node -v) detected${NC}"

# Check if .env exists
echo -e "${BLUE}🔍 Checking environment configuration...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found${NC}"
    echo "Creating .env with default values..."
    cat > .env << EOL
# Backend API URL
VITE_API_URL=http://localhost:5000

# For production, set to your deployed backend:
# VITE_API_URL=https://your-backend.railway.app
EOL
    echo -e "${YELLOW}⚠️  Please update .env with your production backend URL${NC}"
else
    echo -e "${GREEN}✅ .env file found${NC}"
    if grep -q "localhost" .env; then
        echo -e "${YELLOW}⚠️  Warning: .env contains localhost URL${NC}"
        echo "Make sure to set production backend URL before deploying"
    fi
fi

# Clean previous build
echo -e "${BLUE}🧹 Cleaning previous build...${NC}"
rm -rf dist node_modules/.vite

# Install dependencies
echo -e "${BLUE}📦 Installing dependencies...${NC}"
npm install

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ npm install failed${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Check for common issues
echo -e "${BLUE}🔍 Running pre-build checks...${NC}"

# Check if axios is installed
if ! npm list axios > /dev/null 2>&1; then
    echo -e "${RED}❌ axios not found - installing...${NC}"
    npm install axios
fi

# Check if recharts is installed
if ! npm list recharts > /dev/null 2>&1; then
    echo -e "${RED}❌ recharts not found - installing...${NC}"
    npm install recharts
fi

echo -e "${GREEN}✅ All dependencies verified${NC}"

# Run build
echo -e "${BLUE}🏗️  Building frontend...${NC}"
npm run build

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Build failed${NC}"
    echo ""
    echo "Common issues:"
    echo "1. Syntax errors in React components"
    echo "2. Missing dependencies"
    echo "3. Import path errors"
    echo "4. Type errors in JSX"
    echo ""
    echo "Check the error messages above for details."
    exit 1
fi

echo -e "${GREEN}✅ Build completed successfully!${NC}"
echo ""

# Check dist directory
if [ -d "dist" ]; then
    DIST_SIZE=$(du -sh dist | cut -f1)
    echo -e "${GREEN}📊 Build size: $DIST_SIZE${NC}"
    echo ""
    
    # List main files
    echo -e "${BLUE}📄 Generated files:${NC}"
    ls -lh dist/index.html 2>/dev/null && echo "  ✓ index.html"
    ls -lh dist/assets/*.js 2>/dev/null | head -3 && echo "  ✓ JavaScript bundles"
    ls -lh dist/assets/*.css 2>/dev/null | head -3 && echo "  ✓ CSS files"
else
    echo -e "${RED}❌ dist directory not found${NC}"
    exit 1
fi

echo ""
echo "=================================="
echo -e "${GREEN}✅ Deployment Ready!${NC}"
echo "=================================="
echo ""
echo "Next steps:"
echo ""
echo "Option 1: Deploy to Netlify via CLI"
echo "  $ npm install -g netlify-cli"
echo "  $ netlify deploy --prod --dir=dist"
echo ""
echo "Option 2: Deploy via Netlify Dashboard"
echo "  1. Go to: https://app.netlify.com"
echo "  2. Drag and drop the 'dist' folder"
echo "  3. Or connect to GitHub for auto-deploys"
echo ""
echo "Option 3: Deploy via Git"
echo "  $ git add ."
echo "  $ git commit -m 'Frontend build ready'"
echo "  $ git push origin main"
echo "  (Netlify will auto-build if connected)"
echo ""

# Optional: Show .env reminder
if grep -q "localhost" .env 2>/dev/null; then
    echo -e "${YELLOW}⚠️  REMINDER: Update .env with production backend URL${NC}"
    echo -e "${YELLOW}   Current: $(grep VITE_API_URL .env)${NC}"
    echo ""
fi

echo "=================================="
echo -e "${BLUE}📚 Documentation:${NC}"
echo "  - Full audit: ../FINAL_WEB_AUDIT.md"
echo "  - AI features: ../AI_FEATURES_GUIDE.md"
echo "  - Stock fixes: ../STOCK_PERSISTENCE_FIXES.md"
echo "=================================="
