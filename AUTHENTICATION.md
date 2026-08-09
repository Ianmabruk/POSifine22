# Authentication System Documentation

## API Contract

### POST /api/auth/signup
**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass1",
  "name": "User Name",
  "plan": "trial",
  "business_type": "restaurant"
}
```

**Response (201):**
```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "User Name",
    "role": "admin",
    "account_id": "acc_abc123",
    "plan": "trial",
    "active": true,
    "permissions": {...}
  },
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "random-generated-token",
  "csrfToken": "random-csrf-token"
}
```

**Error (400):**
```json
{"error": "Email, password, and name are required"}
```

**Error (429):**
```json
{"error": "Too many signup attempts. Please try again later."}
```

### POST /api/auth/login
**Request:**
```json
{
  "email": "user@example.com",
  "password": "SecurePass1"
}
```

**Response (200):**
```json
{
  "user": { ... },
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "random-generated-token",
  "csrfToken": "random-csrf-token"
}
```

**Error (401):**
```json
{"error": "Invalid credentials"}
```

### POST /api/auth/logout
**Request:**
```json
{
  "refreshToken": "random-generated-token"
}
```

**Headers:**
- `Authorization: Bearer <access_token>`
- `X-CSRF-Token: <csrf_token>`
- Cookie: `csrf_token=<csrf_token>`

**Response (200):**
```json
{"success": true}
```

### POST /api/auth/refresh
**Request:**
```json
{
  "refreshToken": "random-generated-token"
}
```

**Headers:**
- `X-CSRF-Token: <csrf_token>`
- Cookie: `csrf_token=<csrf_token>`

**Response (200):**
```json
{
  "user": { ... },
  "token": "new-access-token",
  "refreshToken": "new-refresh-token",
  "csrfToken": "new-csrf-token"
}
```

### GET /api/auth/me
**Headers:**
- `Authorization: Bearer <access_token>`

**Response (200):**
```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "User Name",
  "role": "admin",
  "account_id": "acc_abc123",
  "plan": "trial",
  "active": true,
  "permissions": {...}
}
```

## Password Security

- **Algorithm**: bcrypt
- **Rounds**: 12 (configurable via `BCRYPT_ROUNDS`, range 4-14)
- **Storage**: `password_hash` column in `users` table
- **Verification**: `bcrypt.checkpw()` on login
- **Never stored**: plaintext passwords, passwords in tokens, passwords in logs

## Rate Limiting

| Endpoint | Limit | Window |
|----------|-------|--------|
| Signup | 5 attempts | 1 hour |
| Login | 5 attempts | 15 minutes |
| Refresh | 30 attempts | 5 minutes |
| Logout | 60 attempts | 2 minutes |

Rate limit key: client IP address

## CSRF Protection

- **Strict paths**: `/api/auth/refresh`, `/api/auth/logout`, `/api/main-admin/auth/refresh`, `/api/main-admin/auth/logout`
- **Requirement**: Both `X-CSRF-Token` header AND `csrf_token` cookie must match
- **Token generation**: `secrets.token_urlsafe(32)` on login/signup/refresh

## Authorization Roles

| Role | Description |
|------|-------------|
| `cashier` | POS operations only |
| `admin` | Full business management |
| `main_admin` | Platform owner, all features |
| `owner` | Same as main_admin |

## Error Format

All errors return JSON:
```json
{
  "error": "Human-readable error message",
  "code": "OPTIONAL_ERROR_CODE"
}
```

Common error codes:
- `TRIAL_EXPIRED` — 403
- `SUBSCRIPTION_EXPIRED` — 403
- `PAYMENT_REQUIRED` — 403

## Cookie Configuration

| Cookie | HttpOnly | Secure | SameSite | Path | Max Age |
|--------|----------|--------|----------|------|---------|
| `refresh_token` | Yes | Yes | None (prod) / Lax (dev) | `/api/auth` | 7 days |
| `csrf_token` | No | Yes | None (prod) / Lax (dev) | `/api/auth` | Session |
