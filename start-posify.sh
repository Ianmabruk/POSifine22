#!/bin/bash

echo "======================================"
echo "   Starting Posify Development        "
echo "======================================"
echo ""

echo ""
echo "Starting backend server..."
cd /home/ian-mabruk/universal
python3 app.py &
BACKEND_PID=$!

echo ""
echo "Starting frontend development server..."
cd /home/ian-mabruk/universal/my-react-app
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
