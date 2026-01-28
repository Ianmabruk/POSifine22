#!/bin/bash
# ==================================================
# Test Runner Script
# ==================================================
# Run all tests with coverage reporting

set -e  # Exit on error

echo "🧪 Running POS Backend Test Suite"
echo "=================================="

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
fi

# Install test dependencies if needed
if ! python -c "import pytest" 2>/dev/null; then
    echo "📦 Installing test dependencies..."
    pip install -q pytest pytest-cov pytest-flask pytest-mock faker
fi

# Run tests
echo ""
echo "🏃 Running tests..."
python -m pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing

# Check if tests passed
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed!"
    echo ""
    echo "📊 Coverage report generated: htmlcov/index.html"
    echo ""
    
    # Open coverage report if on macOS or Linux with GUI
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open htmlcov/index.html
    elif command -v xdg-open &> /dev/null; then
        xdg-open htmlcov/index.html
    fi
else
    echo ""
    echo "❌ Some tests failed"
    exit 1
fi
