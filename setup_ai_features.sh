#!/bin/bash

###############################################################################
# AI FEATURES SETUP SCRIPT
# Installs dependencies and verifies installation
###############################################################################

echo "🚀 Setting up AI Features for POS System..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "ai_service.py" ]; then
    echo -e "${RED}❌ Error: Please run this script from the project root directory${NC}"
    exit 1
fi

echo -e "${YELLOW}📦 Installing Backend Dependencies...${NC}"
echo ""

# Install Python dependencies
pip install openai requests --quiet

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Backend dependencies installed${NC}"
else
    echo -e "${RED}❌ Failed to install backend dependencies${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}📦 Installing Frontend Dependencies...${NC}"
echo ""

# Install React dependencies
cd my-react-app
npm install recharts axios --silent

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Frontend dependencies installed${NC}"
else
    echo -e "${RED}❌ Failed to install frontend dependencies${NC}"
    exit 1
fi

cd ..

echo ""
echo -e "${YELLOW}🔍 Verifying Installation...${NC}"
echo ""

# Verify Python packages
python3 -c "import openai" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ OpenAI package installed${NC}"
else
    echo -e "${YELLOW}⚠️  OpenAI package not found (AI will use fallback mode)${NC}"
fi

python3 -c "import requests" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Requests package installed${NC}"
else
    echo -e "${RED}❌ Requests package missing${NC}"
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo ""
    echo -e "${YELLOW}📝 Creating .env template...${NC}"
    cat > .env << 'EOF'
# AI Features Configuration

# OpenAI API (Optional - uses fallback if not set)
OPENAI_API_KEY=

# Email Alerts
EMAIL_USER=
EMAIL_PASS=
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587

# WhatsApp Alerts (Twilio)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# Database (if using PostgreSQL)
DATABASE_URL=

# JWT Secret
JWT_SECRET=your-secret-key-here
EOF
    echo -e "${GREEN}✅ .env template created${NC}"
    echo -e "${YELLOW}⚠️  Please edit .env and add your API keys${NC}"
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ AI Features Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""

echo "📋 Next Steps:"
echo ""
echo "1. Configure your API keys in .env:"
echo "   nano .env"
echo ""
echo "2. Restart your backend server:"
echo "   cd backend && python app.py"
echo ""
echo "3. Add AI components to your dashboards:"
echo "   - See examples/AdminDashboardIntegration.example.jsx"
echo "   - See examples/ProDashboardIntegration.example.jsx"
echo ""
echo "4. Test the API endpoints:"
echo "   curl http://localhost:5000/api/ai/status"
echo ""
echo "📚 Full documentation: AI_FEATURES_COMPLETE.md"
echo ""

# Check if backend is running
if pgrep -f "python.*app.py" > /dev/null; then
    echo -e "${YELLOW}⚠️  Backend server is running. Please restart it to load AI features.${NC}"
    echo ""
fi
