# Netlify Deployment Guide - CRITICAL FIX

## 🔴 THE PROBLEM YOU'RE EXPERIENCING

**Blank page on Netlify with wrong URL** means:
1. Frontend built successfully ✓
2. Frontend deployed to Netlify ✓
3. BUT: Frontend can't reach backend API ✗
4. Frontend is looking for API at `localhost:5000` (local dev) instead of your production URL

---

## ✅ SOLUTION

### Step 1: Get Your Backend URL

First, determine where your backend is deployed:

**Options:**
- Render: `https://your-app-name.onrender.com/api`
- Railway: `https://your-app.railway.app/api`
- Heroku: `https://your-app.herokuapp.com/api`
- Other: Find your production backend URL

### Step 2: Update .env.production

**File:** `/my-react-app/.env.production`

```dotenv
VITE_API_BASE=https://your-actual-backend-url.onrender.com/api
```

Replace `https://your-actual-backend-url.onrender.com/api` with your real backend URL.

### Step 3: Configure Netlify Dashboard

**In Netlify Dashboard:**

1. Go to your site settings
2. **Build & deploy** → **Environment**
3. Add environment variable:
   - **Key:** `VITE_API_BASE`
   - **Value:** `https://your-backend-url.onrender.com/api`
4. **Save**

### Step 4: Trigger New Deploy

In Netlify:
1. Go to **Deployments**
2. Click **Trigger deploy** → **Deploy site**

---

## 🔧 File Configuration

### .env (Local Development)
```dotenv
VITE_API_BASE=http://localhost:5000/api
```

### .env.local (Local Development Override)
```dotenv
VITE_API_BASE=http://localhost:5000/api
```

### .env.production (Production/Netlify)
```dotenv
VITE_API_BASE=https://your-backend-url.onrender.com/api
```

### netlify.toml (Build Configuration)
```toml
[build]
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

---

## 📋 DEPLOYMENT CHECKLIST

- [ ] Backend is deployed and running
- [ ] Backend URL is accessible: `https://your-backend-url.onrender.com/api/stats`
- [ ] `.env.production` has correct `VITE_API_BASE`
- [ ] Netlify environment variable set in dashboard
- [ ] `netlify.toml` exists in project root
- [ ] `npm run build` runs successfully locally
- [ ] Triggered new deploy on Netlify

---

## 🧪 TEST THE DEPLOYMENT

### 1. Check Frontend Loads
```
Open: https://your-netlify-site.netlify.app
Expected: Dashboard loads (not blank)
```

### 2. Check Console for Errors
```
1. Open https://your-netlify-site.netlify.app
2. Press F12 (DevTools)
3. Go to Console tab
4. Look for errors with "Failed to fetch" or "CORS"
5. Should see [API] logs showing correct backend URL
```

### 3. Verify API Connection
```bash
# Test backend is reachable
curl -H "Authorization: Bearer TOKEN" \
  https://your-backend-url.onrender.com/api/products

# Should return JSON, not error
```

---

## 🔍 DEBUGGING

### If Still Blank After Deploy

1. **Check Netlify Build Logs:**
   - Netlify Dashboard → Deployments → Click latest deploy → View deploy log
   - Look for build errors
   - Look for `VITE_API_BASE` value

2. **Check Frontend Console (F12):**
   - Network tab: Should see API calls to `https://your-backend-url.onrender.com/api/*`
   - NOT to `localhost` or `127.0.0.1`
   - Should see [API] logs with correct URL

3. **Check CORS Headers:**
   ```bash
   curl -i -H "Authorization: Bearer TOKEN" \
     https://your-backend-url.onrender.com/api/stats
   ```
   Should see `Access-Control-Allow-Origin: *`

### If CORS Error

Your backend needs these headers:
```python
# In app.py
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ["*"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    }
)
```

---

## 📝 ENVIRONMENT VARIABLE PRIORITY

Vite uses this priority (highest to lowest):

1. **Netlify Dashboard Environment Variable** (if set)
2. **.env.production** (if build mode is production)
3. **.env** (fallback)

**This means:**
- Local dev uses `.env` or `.env.local` (localhost)
- Netlify build uses `.env.production` (your backend URL)
- Netlify dashboard environment variable overrides `.env.production`

---

## 🚀 QUICK FIX STEPS (5 minutes)

1. **Update .env.production:**
   ```
   VITE_API_BASE=https://your-backend-url.onrender.com/api
   ```

2. **Push to GitHub:**
   ```bash
   git add .env.production netlify.toml
   git commit -m "Fix: Update production API URL for Netlify"
   git push
   ```

3. **Trigger Deploy in Netlify:**
   - Netlify Dashboard → Deployments → Trigger deploy

4. **Wait 1-2 minutes**

5. **Check site:**
   - Open https://your-netlify-site.netlify.app
   - Should NOT be blank
   - Should show dashboard

---

## ⚠️ COMMON MISTAKES

**❌ Mistake 1: Wrong URL Format**
- ❌ `localhost:5000/api` (local only)
- ❌ `127.0.0.1:5000/api` (local only)
- ✅ `https://your-backend-url.onrender.com/api` (production)

**❌ Mistake 2: Missing https://**
- ❌ `your-backend.onrender.com/api`
- ✅ `https://your-backend.onrender.com/api`

**❌ Mistake 3: Trailing slash**
- ❌ `https://your-backend.onrender.com/api/` (extra /)
- ✅ `https://your-backend.onrender.com/api` (no trailing /)

**❌ Mistake 4: Backend not deployed**
- If backend URL doesn't work, all API calls fail
- Test backend first: `curl https://your-backend-url/api/products`

---

## 📞 SUPPORT

If still having issues:

1. **Share your:**
   - Netlify site URL
   - Backend URL
   - Console error message (F12)

2. **Check:**
   - Backend is actually running and accessible
   - Network has no firewall blocking requests
   - CORS is configured on backend

---

**Status:** Ready to deploy

Replace `https://your-backend-url.onrender.com/api` with your actual backend URL and deploy!
