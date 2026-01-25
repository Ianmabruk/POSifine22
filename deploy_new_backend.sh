#!/bin/bash

# ============================================================
# DEPLOY NEW BACKEND
# ============================================================
# This script helps deploy the new POS backend v2.0
#
# Usage:
#   ./deploy_new_backend.sh [mode]
#
# Modes:
#   test     - Test the new backend without affecting production
#   switch   - Switch from old to new backend
#   rollback - Rollback to old backend
# ============================================================

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}→ $1${NC}"
}

log_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

log_error() {
    echo -e "${RED}✗ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi
    
    log_success "Python 3 found"
    
    # Check Python packages
    if python3 -c "import flask, flask_cors, flask_sock, bcrypt, jwt" 2>/dev/null; then
        log_success "All Python packages installed"
    else
        log_warning "Some Python packages missing. Installing..."
        pip install flask flask-cors flask-sock bcrypt pyjwt psycopg psycopg-pool
        log_success "Python packages installed"
    fi
}

# Backup current backend
backup_current() {
    log_info "Backing up current backend..."
    
    if [ -f "app.py" ]; then
        BACKUP_DIR="backups/backup_$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$BACKUP_DIR"
        
        cp app.py "$BACKUP_DIR/app.py"
        
        if [ -d "data" ]; then
            cp -r data "$BACKUP_DIR/data"
        fi
        
        log_success "Backup created at $BACKUP_DIR"
        echo "$BACKUP_DIR" > .last_backup
    else
        log_warning "No existing app.py to backup"
    fi
}

# Test new backend
test_backend() {
    log_info "Testing new backend..."
    
    # Start backend in background
    log_info "Starting backend on port 5001..."
    PORT=5001 python3 app_new.py &
    NEW_BACKEND_PID=$!
    
    # Wait for startup
    sleep 3
    
    # Run tests
    log_info "Running test suite..."
    BASE_URL="http://localhost:5001" python3 test_new_backend.py
    
    # Kill test backend
    kill $NEW_BACKEND_PID 2>/dev/null || true
    
    log_success "Testing complete"
}

# Switch to new backend
switch_backend() {
    log_info "Switching to new backend..."
    
    # Backup current
    backup_current
    
    # Stop old backend if running
    if [ -f "server.pid" ]; then
        OLD_PID=$(cat server.pid)
        if ps -p $OLD_PID > /dev/null; then
            log_info "Stopping old backend (PID: $OLD_PID)..."
            kill $OLD_PID
            sleep 2
        fi
    fi
    
    # Rename files
    if [ -f "app.py" ]; then
        mv app.py app_old.py
        log_info "Old backend saved as app_old.py"
    fi
    
    cp app_new.py app.py
    log_success "New backend activated as app.py"
    
    # Start new backend
    log_info "Starting new backend..."
    python3 app.py &
    echo $! > server.pid
    
    sleep 2
    
    if ps -p $(cat server.pid) > /dev/null; then
        log_success "New backend started successfully!"
        log_info "Backend is running on http://localhost:5000"
    else
        log_error "Failed to start new backend"
        exit 1
    fi
}

# Rollback to old backend
rollback_backend() {
    log_warning "Rolling back to old backend..."
    
    # Stop new backend
    if [ -f "server.pid" ]; then
        PID=$(cat server.pid)
        if ps -p $PID > /dev/null; then
            log_info "Stopping new backend..."
            kill $PID
            sleep 2
        fi
    fi
    
    # Restore old backend
    if [ -f "app_old.py" ]; then
        mv app_old.py app.py
        log_success "Old backend restored"
        
        # Restore data from last backup
        if [ -f ".last_backup" ]; then
            BACKUP_DIR=$(cat .last_backup)
            if [ -d "$BACKUP_DIR/data" ]; then
                log_info "Restoring data from backup..."
                rm -rf data
                cp -r "$BACKUP_DIR/data" data
                log_success "Data restored"
            fi
        fi
        
        # Start old backend
        log_info "Starting old backend..."
        python3 app.py &
        echo $! > server.pid
        
        sleep 2
        
        if ps -p $(cat server.pid) > /dev/null; then
            log_success "Old backend restored successfully!"
        else
            log_error "Failed to start old backend"
            exit 1
        fi
    else
        log_error "No old backend found to restore"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [mode]"
    echo ""
    echo "Modes:"
    echo "  test     - Test the new backend without affecting production"
    echo "  switch   - Switch from old to new backend"
    echo "  rollback - Rollback to old backend"
    echo ""
    echo "Examples:"
    echo "  $0 test     # Test new backend on port 5001"
    echo "  $0 switch   # Switch to new backend"
    echo "  $0 rollback # Rollback to old backend"
}

# Main script
main() {
    echo "============================================================"
    echo "POS Backend Deployment Script v2.0"
    echo "============================================================"
    echo ""
    
    MODE="${1:-test}"
    
    case "$MODE" in
        test)
            check_dependencies
            test_backend
            ;;
        switch)
            check_dependencies
            log_warning "This will switch to the new backend!"
            read -p "Are you sure? (yes/no) " -n 3 -r
            echo
            if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                switch_backend
            else
                log_info "Cancelled"
                exit 0
            fi
            ;;
        rollback)
            log_warning "This will rollback to the old backend!"
            read -p "Are you sure? (yes/no) " -n 3 -r
            echo
            if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                rollback_backend
            else
                log_info "Cancelled"
                exit 0
            fi
            ;;
        *)
            show_usage
            exit 1
            ;;
    esac
    
    echo ""
    echo "============================================================"
    log_success "Done!"
    echo "============================================================"
}

# Run main
main "$@"
