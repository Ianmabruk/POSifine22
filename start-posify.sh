#!/bin/bash

echo "======================================"
echo "   Starting Posify Development        "
echo "======================================"
echo ""

# Check if MongoDB is running
if ! pgrep -x "mongod" > /dev/null; then
    echo "Starting MongoDB..."
    mongod --dbpath /data/db --fork --logpath /var/log/mongod.log 2>/dev/null || {
        echo "Warning: Could not start MongoDB. Please ensure MongoDB is installed and running."
        echo "You can start MongoDB with: mongod --dbpath /data/db"
    }
else
    echo "MongoDB is already running."
fi

echo ""
echo "Starting backend server..."
cd backend-express
npm run dev &
BACKEND_PID=$!

echo ""
echo "Starting frontend development server..."
cd ../my-react-app
npm run dev &
FRONTEND_PID=$!

echo ""
echo "======================================"
echo "   Posify is starting up               "
echo "======================================"
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT
wait
