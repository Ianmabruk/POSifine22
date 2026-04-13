# Production Security Checklist Pass

Date: 2026-04-13
Scope: auth, session, CORS, and rate-limit endpoints in root and backend app entrypoints.

## Build Status
- TypeScript backend build: PASS (`npm run -s build`, exit code `0`).
- Previous TS errors were resolved in:
  - `src/database/mysql/client.ts`
  - `src/database/mysql/generated.ts`
  - `src/database/sqlite/generated.ts`
  - `src/modules/products/products.repository.ts`
  - `src/modules/sync/sync.service.ts`

## Strict Production Checklist

### Authentication and Token Handling
- [x] No default secrets in production.
  - Current status: PASS (startup now fails in production if `JWT_SECRET`/`SECRET_KEY` is missing).
- [ ] Access tokens are short-lived and verified with explicit algorithms.
  - Current status: PASS (`HS256`, 20 minute access token).
- [x] Refresh tokens are never exposed to JavaScript unless absolutely required.
  - Current status: PASS (refresh token moved to `HttpOnly` cookie in login/signup/refresh responses).
- [ ] Main-admin login has no production backdoor/bootstrap path.
  - Current status: PASS (DB-backed role and password verification required in non-dev mode).

### Session Management
- [ ] Refresh sessions are hashed at rest.
  - Current status: PASS (SHA-256 hash stored).
- [ ] Session revoke and rotation are implemented.
  - Current status: PASS.
- [ ] Device/IP binding checks are enforced on refresh/reuse.
  - Current status: PARTIAL (metadata stored, not enforced).

### CSRF Controls
- [x] State-changing endpoints require CSRF validation.
  - Current status: PASS/PARTIAL (strict CSRF required for `/api/auth/refresh` and `/api/auth/logout`; legacy non-auth behavior retained).
- [x] CSRF token is validated for refresh and logout endpoints.
  - Current status: PASS.

### CORS Controls
- [x] Production origin allowlist is explicit and minimal.
  - Current status: PASS (production startup now rejects `CORS_ORIGINS="*"`).
- [x] Credentialed CORS does not combine wildcard origins.
  - Current status: PASS (wildcard branch now disables credentials and is non-production only).
- [x] Allowed methods/headers are explicitly set.
  - Current status: PASS.

### Rate Limiting and Abuse Protection
- [ ] Login endpoints are rate-limited with lockout window.
  - Current status: PASS.
- [x] Refresh and logout endpoints have abuse throttling.
  - Current status: PASS.
- [x] Rate-limit key cannot be spoofed by client headers.
  - Current status: PASS/PARTIAL (`X-Forwarded-For` is only trusted when proxy trust is explicitly enabled or caller is a trusted proxy IP).

## Remaining Findings
1. Enforce or verify trusted proxy configuration in deployment (`TRUST_PROXY_HEADERS`, `TRUSTED_PROXY_IPS`).
2. Validate frontend clients now send credentials and CSRF headers for refresh/logout in all environments.

## Recommended Next Hardening Steps
1. Add automated integration tests for cookie-based refresh flow (including CSRF mismatch and retry-after behavior).
2. Set and document production values for `CORS_ORIGINS`, `AUTH_COOKIE_SAMESITE`, `TRUST_PROXY_HEADERS`, and `TRUSTED_PROXY_IPS`.
3. Keep root and backend app entrypoint security settings aligned to avoid environment drift.
