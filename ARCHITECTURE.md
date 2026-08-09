# POSify — Authentication & Multi-Server Architecture

## CURRENT ARCHITECTURE

| Component | Details |
|-----------|---------|
| **Frontend** | React + Vite, deployed to Netlify (`posifine11.netlify.app`) |
| **Backend** | Python Flask, deployed to Render (`posifine22.onrender.com`) |
| **Database** | Neon PostgreSQL (serverless, pooled connections) |
| **Auth** | JWT access tokens (15min) + HTTP-only refresh tokens (7 days) + bcrypt passwords |
| **Single Server** | Render web service running one Flask process |

### Problems with Current Architecture
1. **Database connection pool exhaustion**: `psycopg_pool` with `min_size=2, max_size=5` against slow Neon pooler causes stale connections → 500 errors on auth
2. **No horizontal scaling**: Single server instance, single point of failure
3. **CORS misconfiguration**: `CORS_ORIGIN` didn't include `localhost:3000`
4. **Stock race conditions**: Delta-based `UPDATE products SET quantity = quantity - %s` without `WHERE quantity >= %s` allows negative inventory
5. **Logout CSRF strictness**: Requires both cookie and header for `/api/auth/logout`
6. **WebSocket 404**: Frontend expects `/ws` WebSocket endpoint that Flask doesn't provide

---

## NEW ARCHITECTURE

```
                     INTERNET
                        |
                        ▼
                 LOAD BALANCER (port 8080)
                        |
          ┌─────────────┼─────────────┐
          │             │             │
          ▼             ▼             ▼
    AUTH SERVER     API SERVER 1   API SERVER 2
    (port 8081)     (port 8082)    (port 8083)
          │             │             │
          └─────────────┼─────────────┘
                        │
                        ▼
                SHARED SERVICES
                        |
          ┌─────────────┴─────────────┐
          ▼                           ▼
   PostgreSQL / Neon              Redis (optional)
   Shared database              Shared state
```

### Server Responsibilities

| Server | Port | Responsibility |
|--------|------|----------------|
| **AUTH-1** | 8081 | `/api/auth/*` — signup, login, logout, refresh, me, pin-login, change-password, lock-screen, unlock-screen |
| **API-1** | 8082 | `/api/products/*`, `/api/sales/*`, `/api/inventory`, `/api/dashboard/*`, `/api/settings/*`, `/api/expenses/*`, `/api/reminders/*`, `/api/users/*`, etc. |
| **API-2** | 8083 | Same as API-1 (identical code, different process) |
| **Load Balancer** | 8080 | Routes `/api/auth/*` → AUTH-1, everything else → round-robin API-1/API-2 |

### Key Design Principles
1. **Shared Database**: All servers connect to the same Neon PostgreSQL instance
2. **Stateless API Servers**: API-1 and API-2 store no session state in memory
3. **Shared JWT Secret**: All servers use the same `JWT_SECRET` for token verification
4. **Server Identification**: Every response includes `X-Server-ID` and `X-Server-Mode` headers
5. **Health Checks**: Every server exposes `/health` endpoint
6. **Route Filtering**: `SERVER_MODE` env var controls which routes are active on each server

---

## AUTHENTICATION REBUILD

### Token Architecture
```
Access Token (JWT)
  - Short-lived: 15 minutes (JWT_EXPIRES_IN=15m)
  - Stateless: signed with HS256 using JWT_SECRET
  - Minimal claims: jti, user_id, email, account_id, role, exp, iat
  - Stored in localStorage (frontend) + verified by all servers

Refresh Token
  - Long-lived: 7 days
  - Stored as HTTP-only cookie + localStorage
  - Hashed (SHA-256) before database storage
  - Revocable: server marks session as revoked
  - Rotated: each refresh creates a new session
```

### Authentication Flow

```
SIGNUP
  Frontend → POST /api/auth/signup
    → AUTH-1 validates input
    → Checks duplicate email
    → Hashes password (bcrypt, rounds=12)
    → Creates account + user in PostgreSQL (single transaction)
    → Creates JWT access token
    → Creates refresh session (hashed token stored in DB)
    → Returns { user, token, refreshToken, csrfToken }
    → Sets HTTP-only cookies for refresh_token + csrf_token
    → Frontend stores token in localStorage, redirects to dashboard

LOGIN
  Frontend → POST /api/auth/login
    → AUTH-1 rate limits (5 attempts/15min)
    → Looks up user by email
    → Verifies password with bcrypt
    → Checks account active/not locked
    → Creates JWT access token
    → Creates refresh session
    → Returns { user, token, refreshToken, csrfToken }
    → Frontend stores tokens, redirects to dashboard

SESSION RESTORATION
  Frontend on load:
    → Reads token from localStorage
    → GET /api/auth/me (with Authorization header)
    → If 200: user is authenticated
    → If 401: POST /api/auth/refresh (with refreshToken)
      → AUTH-1 validates refresh session
      → Creates new access token + new refresh session
      → Returns new tokens
    → If refresh fails: clear localStorage, redirect to login

LOGOUT
  Frontend → POST /api/auth/logout
    → Requires X-CSRF-Token header + csrf_token cookie
    → AUTH-1 revokes refresh session (marks revoked_at)
    → AUTH-1 revokes access token (adds jti to revoked set)
    → Clears HTTP-only cookies
    → Frontend clears localStorage
```

### Security Measures
1. **Password Hashing**: bcrypt with 12 rounds (configurable via `BCRYPT_ROUNDS`)
2. **Rate Limiting**: Login 5/15min, Signup 5/hour, Refresh 30/5min, Logout 60/2min
3. **CSRF Protection**: Strict CSRF check on `/api/auth/logout` and `/api/auth/refresh` (requires both cookie and header)
4. **CORS**: Dynamic origin allowlist + `*.netlify.app` wildcard + `credentials: true`
5. **HTTP-only Cookies**: Refresh tokens stored in HTTP-only, Secure, SameSite cookies
6. **Token Revocation**: Revoked tokens tracked in-memory (server-local) + refresh sessions marked revoked in DB
7. **Input Validation**: Email normalization, password strength enforcement
8. **No Plaintext Passwords**: Passwords never logged, never returned in responses, never stored in tokens

---

## DATABASE CHANGES

### Connection Pool Fix
**File**: `database.py:110-147`

```python
# Before (broken):
ConnectionPool(db_url, min_size=2, max_size=5, timeout=10, max_lifetime=1800)

# After (fixed):
ConnectionPool(db_url, min_size=2, max_size=5, timeout=30, max_lifetime=300)
# + removed channel_binding=require
# + added connect_timeout=10
# + added SELECT 1 validation in _pg_connection()
```

### Stock Concurrency Fix
**File**: `stock_engine.py:402-409`

```python
# Before (race condition):
UPDATE products SET quantity = quantity - %s, updated_at = %s
WHERE id = %s AND account_id = %s

# After (atomic):
UPDATE products SET quantity = quantity - %s, updated_at = %s
WHERE id = %s AND account_id = %s AND quantity >= %s
# + check cur.rowcount == 0 → return "Insufficient stock"
```

### CORS Fix
**File**: `.env`

```env
# Before:
CORS_ORIGIN=http://localhost:5173

# After:
CORS_ORIGIN=http://localhost:5173,http://localhost:3000
```

### Server Mode Middleware
**File**: `app.py:134-167`

Added `SERVER_MODE` env var support:
- `SERVER_MODE=auth` → only auth routes active
- `SERVER_MODE=api` → all routes except auth mutations active
- `SERVER_MODE` unset → full app (backward compatible)

---

## FRONTEND CHANGES

**No frontend code changes required.** The rebuilt backend maintains full compatibility with the existing frontend.

The only change is `.env`:
```env
VITE_API_BASE=http://localhost:8080/api  # Points to load balancer
```

---

## SERVER ARCHITECTURE DETAILS

### AUTH SERVER (port 8081)
- Handles: `/api/auth/signup`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/refresh`, `/api/auth/me`, `/api/auth/pin-login`, `/api/auth/change-password`, `/api/auth/lock-screen`, `/api/auth/unlock-screen`
- Does NOT handle: products, sales, inventory, dashboard, settings
- Server ID: `AUTH-1`
- Server Mode: `auth`

### API SERVER 1 (port 8082)
- Handles: all business logic routes
- Also handles: `/api/auth/me` and `/api/auth/refresh` (for session validation)
- Server ID: `API-1`
- Server Mode: `api`

### API SERVER 2 (port 8083)
- Identical to API SERVER 1
- Server ID: `API-2`
- Server Mode: `api`

### LOAD BALANCER (port 8080)
- Simple round-robin proxy
- Routes `/api/auth/*` → AUTH-1
- Routes everything else → API-1 or API-2
- Health checks every 5 seconds
- Removes unhealthy backends from rotation

---

## DEPLOYMENT ARCHITECTURE

### Local Development
```
Frontend (Vite) → Load Balancer (8080) → AUTH-1 (8081) / API-1 (8082) / API-2 (8083)
```

### Production (Render)
```
Internet → Render Load Balancer → AUTH-1 (Render Web Service) → Neon PostgreSQL
                                         → API-1 (Render Web Service) ↗
                                         → API-2 (Render Web Service) ↗
```

### Environment Variables
```env
# Shared across all servers
DATABASE_URL=postgresql://...
JWT_SECRET=<shared-secret>
JWT_EXPIRES_IN=15m
BCRYPT_ROUNDS=12
CORS_ORIGINS=https://posifine11.netlify.app,https://posifine-frontend.netlify.app

# AUTH-1 specific
SERVER_MODE=auth
SERVER_ID=AUTH-1
PORT=8081

# API-1 specific
SERVER_MODE=api
SERVER_ID=API-1
PORT=8082

# API-2 specific
SERVER_MODE=api
SERVER_ID=API-2
PORT=8083
```

---

## HEALTH CHECKS

All servers expose:
- `GET /health` — returns `{"status": "ok", "services": {"database": "postgres"}}`
- `GET /ready` — same as health

Load balancer checks health every 5 seconds and removes unhealthy backends.

---

## SCALING STRATEGY

1. **Horizontal scaling**: Add more API servers by starting additional processes on new ports
2. **Load balancer**: Add new backend URLs to `API_BACKENDS` list
3. **Database connection budget**: 3 servers × 5 max connections = 15 total (well within Neon limits)
4. **Stateless design**: Any API server can handle any request; no sticky sessions required
5. **Zero-downtime deploys**: Remove server from load balancer, deploy, re-add

---

## FAILURE HANDLING

| Failure | Behavior |
|---------|----------|
| AUTH-1 crashes | Users cannot log in/sign up, but existing sessions continue on API servers |
| API-1 crashes | Load balancer routes all traffic to API-2 |
| API-2 crashes | Load balancer routes all traffic to API-1 |
| Database unavailable | All servers return 500 with "Database not available" |
| Neon pool exhaustion | Connection retry with SELECT 1 validation; falls back to JSON storage if Postgres init fails |

---

## ROLLBACK STRATEGY

1. Set `SERVER_MODE=` (empty) in all server env vars → full app mode (original behavior)
2. Single process on single port (e.g., 8080)
3. All routes active, no filtering
4. Backward compatible with original `app.py`

---

## AUTHENTICATION.md

See `AUTHENTICATION.md` for detailed documentation of:
- Signup flow
- Login flow
- Logout flow
- Token refresh flow
- Password security
- Rate limiting
- CSRF protection
- Authorization roles
- Error handling
