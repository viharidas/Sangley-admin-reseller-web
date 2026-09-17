# Authentication checks
Use the external REACT_APP_BACKEND_URL for all API checks.
1. Confirm MongoDB admin has a bcrypt $2b$ password hash and users.email unique index.
2. Use credentials in /app/memory/test_credentials.md to POST /api/auth/login; verify secure HttpOnly access and refresh cookies.
3. GET /api/auth/me with cookies must return admin; without cookies must return 401.
4. Confirm admin products/content/orders/leads/export endpoints reject unauthenticated requests.
5. Authenticated mutations validate Origin against the explicit SANGLEY_TRUSTED_ORIGINS environment allowlist shared with CORS. It contains this site's public origin and the observed gateway-rewritten origin. Invalid origins must fail. Never use wildcard origin exemptions.
6. Invalid login returns a string error, never a UI crash. Five failed logins lock the normalized account identity for fifteen minutes across all gateway nodes; the sixth returns 429. The account-scoped key prevents rotating proxy addresses from splitting attempts. Reseller password login uses the same stable account-scoped approach.
7. Refresh issues a new access token. Logout clears both cookies. No public registration endpoint.