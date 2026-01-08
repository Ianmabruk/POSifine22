# Backend Deployment Guide

## Overview

This is a **Python Flask** backend for the POSifine POS system. It's production-ready and can be deployed to Render, Railway, Heroku, or any Docker-capable host.

---

## Quick Deploy (Render.com - Recommended)

### Step 1: Connect Repository
1. Go to https://render.com
2. Click "New +" → "Web Service"
3. Connect your GitHub account
4. Select **POSifine22** repository

### Step 2: Configure Service
- **Name:** posifine-backend
- **Environment:** Python
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -w 4 -b 0.0.0.0:5000 app:app`

### Step 3: Set Environment Variables
Click "Add Environment Variable" and add:

| Key | Value | Notes |
|-----|-------|-------|
| `JWT_SECRET` | Generate a strong random string (32+ chars) | Use: `openssl rand -hex 32` |
| `FLASK_ENV` | `production` | Sets Flask to production mode |
| `PYTHONUNBUFFERED` | `1` | Ensures Python output is not buffered |

### Step 4: Deploy
Click "Deploy" and wait 3-5 minutes. Your backend will be live at:
```
https://posifine-backend.onrender.com
```

---

## Local Testing

### Prerequisites
```bash
pip install -r requirements.txt
```

### Run Locally
```bash
export JWT_SECRET="test-secret-key-32-characters-long"
python app.py
```

The backend will run on `http://localhost:5000`

### Test Endpoints
```bash
# Health check
curl http://localhost:5000/

# Signup
curl -X POST http://localhost:5000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123","name":"Test"}'

# Login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123"}'
```

---

## Deployment Platforms

### 1. Render.com (Recommended)
- **Pros:** Easy setup, good free tier, great UI
- **Cost:** Free tier available
- **Time:** 5 minutes
- **Process:** See Quick Deploy section above

### 2. Railway.app
```bash
# Install Railway CLI
npm i -g railway

# Login and deploy
railway up
```

**Railway.json is pre-configured!**

### 3. Heroku
```bash
# Install Heroku CLI
brew tap heroku/brew && brew install heroku

# Login
heroku login

# Create app
heroku create posifine-backend

# Set environment variables
heroku config:set JWT_SECRET="your-secret-key"
heroku config:set FLASK_ENV=production

# Deploy
git push heroku main
```

**Procfile is included:**
```
web: gunicorn -w 4 -b 0.0.0.0:$PORT app:app
```

### 4. Docker (Any Cloud Provider)
```bash
# Build image
docker build -t posifine-backend .

# Run locally to test
docker run -p 5000:5000 \
  -e JWT_SECRET="test-secret" \
  posifine-backend

# Push to Docker Hub
docker tag posifine-backend username/posifine-backend
docker push username/posifine-backend

# Deploy on Render, Railway, AWS, etc.
```

---

## API Endpoints

### Authentication
- `POST /api/auth/signup` - Create new user
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user

### Products
- `GET /api/products` - List all products
- `POST /api/products` - Create product (admin only)
- `PUT /api/products/{id}` - Update product (admin only)
- `DELETE /api/products/{id}` - Delete product (admin only)

### Sales
- `GET /api/sales` - List all sales
- `POST /api/sales` - Create sale (cashier)

### Users
- `GET /api/users` - List all users (admin only)
- `POST /api/users` - Create user (admin only)
- `PUT /api/users/{id}` - Update user (admin only)

### WebSocket
- `WS /api/ws/products` - Real-time product updates

---

## Environment Variables

**Required:**
- `JWT_SECRET` - Secret key for JWT tokens (min 32 chars)

**Optional:**
- `FLASK_ENV` - `production` or `development` (default: `development`)
- `FLASK_DEBUG` - `0` or `1` (default: `0`)
- `PORT` - Port to run on (default: `5000`)

---

## Troubleshooting

### 404 Errors on Deployed Backend
**Cause:** Data directory not initialized
**Fix:** Data directory is created automatically on first run

### CORS Errors
**Cause:** Frontend domain not allowed
**Fix:** CORS is enabled for all origins by default in production

### JWT Token Errors
**Cause:** JWT_SECRET not set or different between deployments
**Fix:** Ensure JWT_SECRET is the same across all deployments

### Backend Won't Start
**Cause:** Missing dependencies or Python version issue
**Fix:** 
```bash
pip install -r requirements.txt
python app.py
```

---

## Production Checklist

- [ ] JWT_SECRET is a strong random string (32+ chars)
- [ ] FLASK_ENV set to `production`
- [ ] Backend deployed to production URL
- [ ] Health check endpoint responds: `curl https://backend-url/`
- [ ] CORS configured for frontend domain
- [ ] SSL/TLS certificate enabled (HTTPS)
- [ ] Database backups configured (if using)
- [ ] Error logging setup (Sentry, LogRocket)
- [ ] Monitoring alerts configured
- [ ] Load testing completed

---

## Performance

**Default Configuration:**
- Workers: 4 (for standard deployments)
- Timeout: 120 seconds
- Keep-alive: 5 seconds

**For High Traffic:**
- Increase workers: `gunicorn -w 8` (or 2 x CPU cores)
- Use PostgreSQL instead of file-based storage
- Add Redis for caching
- Setup load balancing

---

## Support

**Documentation:**
- Backend API: See endpoints section above
- Frontend: Check frontend repository
- Deployment: See platform-specific guides

**Quick Links:**
- Render: https://render.com
- Railway: https://railway.app
- Heroku: https://heroku.com

---

## Next Steps

1. **Deploy backend** using Render (5 minutes)
2. **Note the backend URL** (e.g., https://posifine-backend.onrender.com)
3. **Deploy frontend** with backend URL
4. **Test complete flow:** Signup → Login → Create sale
5. **Enable monitoring** for production

---

**Backend is production-ready! Deploy whenever you're ready.** 🚀
