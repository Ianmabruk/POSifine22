# Render.com Deployment Troubleshooting

## Issue: 500 Error After Deployment

If you're seeing **500 errors** after deploying on Render, follow these steps:

---

## Step 1: Check Render Logs

1. Go to https://render.com
2. Click on **posifine-backend** service
3. Click **Logs** tab
4. Look for error messages in the output

Common errors:
```
ModuleNotFoundError: No module named 'flask'
→ Fix: Dependencies not installed. Check "Build Command"

KeyError: 'JWT_SECRET'
→ Fix: JWT_SECRET not set in environment variables

PermissionError: [Errno 13] Permission denied: 'data'
→ Fix: Data directory creation failed. Check file permissions
```

---

## Step 2: Verify Environment Variables

1. Go to your service → **Settings** → **Environment**
2. Confirm these are set:

| Variable | Value | Status |
|----------|-------|--------|
| `JWT_SECRET` | Random string (32+ chars) | ✅ Must be set |
| `FLASK_ENV` | `production` | ✅ Must be set |
| `PYTHONUNBUFFERED` | `1` | ✅ Recommended |

**If JWT_SECRET is empty or missing:**
1. Click **Add Environment Variable**
2. Key: `JWT_SECRET`
3. Value: Generate with: `openssl rand -hex 32`
4. Click **Save**
5. Service will redeploy automatically

---

## Step 3: Redeploy with Latest Code

If you just pushed the fix:

1. Go to **Deployments** tab
2. Click **Manual Deploy** button
3. Select the latest commit
4. Wait 3-5 minutes for deployment

Or simply push to GitHub and it auto-deploys.

---

## Step 4: Test Backend Health

Once redeployed, test the backend:

```bash
# Replace with your Render URL
BACKEND_URL="https://posifine-backend.onrender.com"

# Test health check
curl $BACKEND_URL/

# Should return:
# {
#   "message": "POS API is running",
#   "storage": "file-based",
#   "status": "healthy",
#   "database": "none"
# }
```

---

## Step 5: Check Frontend Configuration

Make sure your frontend points to the correct backend URL:

**In Frontend Environment Variables:**
```
VITE_API_BASE=https://posifine-backend.onrender.com/api
VITE_API_URL=https://posifine-backend.onrender.com
```

**Not:**
```
VITE_API_BASE=http://localhost:5000/api  ❌ Wrong
VITE_API_URL=http://localhost:5000       ❌ Wrong
```

---

## Common Issues & Solutions

### Issue: Still Getting 500 Errors

**Check 1: Data Directory Permissions**
```bash
# In Render logs, you should see:
# ✅ Data files initialized
# ✅ Using file storage at: /app/data
```

If you don't see these, the startup script failed.

**Solution:** Manually redeploy:
1. Go to Deployments
2. Click the three dots ⋮ on latest deployment
3. Click "Rerun"
4. Wait 5 minutes

**Check 2: JWT_SECRET is Set**
```bash
# Test login endpoint with missing JWT_SECRET
curl -X POST https://posifine-backend.onrender.com/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"test","name":"Test"}'

# If it returns 500 with KeyError: JWT_SECRET
# → JWT_SECRET not set!
```

**Solution:** Add JWT_SECRET in Environment Variables.

### Issue: "Authentication error: Error: Server error 500"

This error on the frontend means:

1. **Backend is returning 500** (likely JWT_SECRET issue)
2. **OR Backend is not accessible** (frontend URL wrong)

**Fix:**
1. ✅ Set JWT_SECRET in Render environment
2. ✅ Verify VITE_API_BASE in frontend is correct
3. ✅ Test backend health: `curl https://backend-url/`

### Issue: "Port Already in Use"

This shouldn't happen on Render (they auto-assign PORT).

If you see this, the port variable might be hardcoded.

**Check:** In app.py line ~380:
```python
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=port)
```

Should use `os.environ.get('PORT')` not hardcoded port.

### Issue: Timeout (504 Gateway Timeout)

**Cause:** Request taking too long or backend not responding

**Solutions:**
1. Check if backend is still running in Render
2. Restart service: Deployments → Rerun
3. Check logs for crash/error messages

---

## Step 6: Verify Complete Flow

After backend is working:

1. **Health Check:**
   ```bash
   curl https://your-backend.onrender.com/
   # Should return 200 with healthy status
   ```

2. **Signup:**
   ```bash
   curl -X POST https://your-backend.onrender.com/api/auth/signup \
     -H "Content-Type: application/json" \
     -d '{"email":"test@posifine.com","password":"Test123!","name":"Test User"}'
   # Should return 200 with JWT token
   ```

3. **Frontend Test:**
   - Open frontend URL
   - Try to Signup
   - Should redirect to Dashboard
   - Can see products and other features

---

## Still Having Issues?

### Get Full Logs

1. Go to Render dashboard
2. Click **posifine-backend**
3. Click **Logs** tab
4. Copy all errors
5. Share with support

### Check start.sh

The fix uses a new `start.sh` script. If it wasn't deployed:

1. Make sure you pulled latest from GitHub
2. Do a manual redeploy on Render
3. Wait 5+ minutes

### Force Redeploy

1. Go to **Deployments** tab
2. Click ⋮ on latest deployment
3. Click "Rerun"
4. Or: Go to **Settings** → **Git Repository** → **Manual Deploy** with specific branch

---

## Success Indicators ✓

After fixing, you should see in Render logs:

```
🚀 Starting POSifine Backend on Render...
✅ Data files initialized
📦 Starting Gunicorn on port [PORT]...
Listening on 0.0.0.0:[PORT]
[timestamp] [PID] [INFO] Application startup complete [Uvicorn]
```

And in browser:
```
GET https://posifine-backend.onrender.com/
Status: 200

Response:
{
  "message": "POS API is running",
  "status": "healthy",
  "storage": "file-based"
}
```

---

## Quick Summary

Your **500 error** is likely caused by:

1. **JWT_SECRET not set** (90% of the time)
   → Add to Render Environment Variables

2. **Data files not created** (8% of the time)
   → Redeploy with latest code that has `start.sh`

3. **Frontend pointing to wrong URL** (2% of the time)
   → Update VITE_API_BASE in frontend

**Action:**
1. Set JWT_SECRET in Render
2. Redeploy
3. Test: `curl https://your-backend.onrender.com/`
4. Update frontend API URL
5. Done! ✓

---

**Need help? Check Render logs first - they usually show exactly what's wrong!**
