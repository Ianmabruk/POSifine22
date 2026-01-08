# Backend Deployment - Troubleshooting 404 Errors

## Fix for 404 Errors

The 404 errors are caused by missing data files in the `data/` directory on the deployed server. Here's the fix:

### 1. **Ensure data/ directory is created**

The backend now automatically creates the `data/` directory and initializes all JSON files on startup.

### 2. **Deploy with these steps:**

#### Option A: Render.com (Recommended)

```bash
# 1. Go to https://render.com
# 2. Create new Web Service
# 3. Connect GitHub: POSifine22
# 4. Configure:
#    - Root directory: ./backend
#    - Build command: pip install -r requirements.txt
#    - Start command: gunicorn -w 4 -b 0.0.0.0:5000 app:app
# 5. Environment Variables:
#    - JWT_SECRET: (strong random 32+ char string)
#    - FLASK_ENV: production
# 6. Deploy

# The backend will automatically:
# - Create the data/ directory
# - Initialize all JSON files
# - Start serving API requests
```

#### Option B: Railway.app

```bash
# 1. Go to https://railway.app
# 2. Create new project
# 3. Deploy from GitHub: POSifine22
# 4. Configure:
#    - Root directory: backend
#    - Build: pip install -r requirements.txt
#    - Start: python app.py
# 5. Set JWT_SECRET env var
# 6. Deploy
```

### 3. **Test after deployment:**

```bash
# Test health endpoint
curl https://your-backend-url/
# Should return: {"message":"POS API is running","status":"healthy",...}

# Test signup
curl -X POST https://your-backend-url/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123","name":"Test User","plan":"ultra"}'
# Should return JWT token

# Test products (after signup/login)
TOKEN="your-jwt-token-here"
curl https://your-backend-url/api/products \
  -H "Authorization: Bearer $TOKEN"
# Should return: [] (empty array initially)
```

### 4. **If still getting 404 errors:**

#### Check 1: Verify backend is running
```bash
curl https://your-backend-url/
# Must return JSON response, not 404
```

#### Check 2: Check data directory permissions
On production server, ensure `backend/data/` directory is writable:
```bash
chmod -R 755 backend/data/
```

#### Check 3: Verify environment variables
```bash
# Check if JWT_SECRET is set
echo $JWT_SECRET
# Must not be empty
```

#### Check 4: Check logs
Look for these messages on startup:
```
✅ Using file storage at: /app/backend/data
✅ Data files initialized
```

### 5. **Updated Backend Features:**

✅ Automatic data directory initialization  
✅ Automatic JSON file creation on startup  
✅ Production-ready error handlers  
✅ 404 endpoint error messages  
✅ Environment variable PORT support  
✅ CORS enabled for all origins  
✅ Token validation with OPTIONS support  

### 6. **Commit and push updated backend:**

```bash
cd backend
git add app.py init_data.sh requirements.txt
git commit -m "fix: Auto-initialize data files on startup, add error handlers"
git push origin main
```

### 7. **If deployment already exists:**

Redeploy your backend:

**Render:** Go to Deployments → Trigger deploy → Redeploy latest commit

**Railway:** Go to Deployments → Redeploy

**Heroku:** `git push heroku main`

---

## Successful Deployment Checklist

After deployment verify:

- [ ] `curl https://backend-url/` returns `{"status":"healthy",...}`
- [ ] No 404 errors on health check
- [ ] Can POST to `/api/auth/signup`
- [ ] Receive JWT token on signup
- [ ] Can GET `/api/products` with Bearer token
- [ ] Products endpoint returns empty array initially
- [ ] Can POST new product and see it returned
- [ ] Sales endpoint working
- [ ] Admin dashboard connects without errors

---

## Still Getting 404?

**Common causes:**
1. **Wrong URL** - Check backend URL is correct (including `https://`)
2. **Data dir not writable** - Check permissions on server
3. **Flask not started** - Check deployment logs for errors
4. **CORS not working** - Frontend must use `https://` for backend
5. **PORT mismatch** - Backend should be on 5000 or custom PORT env var

**Solution:**
- Check deployment logs
- Verify `data/` directory exists on server
- Ensure `JWT_SECRET` is set
- Restart the deployment

---

## API Endpoints Available

```
POST   /api/auth/signup          - Create new user
POST   /api/auth/login           - Login user
GET    /api/auth/me              - Current user
GET    /api/products             - Get all products
POST   /api/products             - Create product
PUT    /api/products/:id         - Update product
DELETE /api/products/:id         - Delete product
GET    /api/users                - Get all users
POST   /api/users                - Create user
GET    /api/sales                - Get all sales
POST   /api/sales                - Create sale
GET    /api/stats                - Get statistics
GET    /api/settings             - Get settings
POST   /api/settings             - Update settings
GET    /api/reminders/today      - Get today's reminders
GET    /api/discounts            - Get discounts
WS     /api/ws/products          - WebSocket product sync
```

---

## Need Help?

1. Check deployment logs for errors
2. Test with `curl` commands above
3. Verify all environment variables are set
4. Ensure `data/` directory exists and is writable
5. Check backend is listening on the correct port

**The backend is now production-ready! 🚀**
