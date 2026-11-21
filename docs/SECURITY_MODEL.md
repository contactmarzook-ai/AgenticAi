# Security model

Everything below is enforced by the API. The web app only hides what a user cannot use, and is
not relied on for access control. Tests: `backend/tests/test_tenancy_auth.py` (plus
`test_auth_rbac.py` and `test_phase1_security.py`).

## Organizations (tenants)

- Every user belongs to exactly one organization, fixed when the user is created.
- Every agent, workflow, run, trigger and connection carries the `org_id` of the person who created
  it. Audit rows carry the organization they concern.
- A resource of another organization is **not found** (404) for everyone, including platform
  admins and org admins. This applies to reads, edits, runs, duplicates, re-runs, connection
  usage/tests, trigger changes, chat sessions and list endpoints. Ids from another organization used
  *inside* a workflow (a connection or an agent) are reported as "no longer exists" at validation
  and refused at run time.
- Platform admins manage **organizations and users** across tenants and see the whole audit log;
  they do not see another organization's agents, workflows, runs or connections.
- Deactivating an organization signs out all its users immediately and blocks sign-in.
- Shared platform resources: LLM providers/models and platform settings (managed by platform
  admins). Agents' tools are code in the image, not tenant data.
- There are no document/knowledge stores yet; when added they must carry `org_id` the same way.

Existing data migrates into "Default organization" (id 1); roles are renamed
`admin → platform_admin`, `builder → developer`, `user → operator`
(`alembic/versions/a1c3e5f7b9d2_tenants_roles_sessions.py`).

## Roles

| Permission | Viewer | Operator | Developer | Auditor | Org admin | Platform admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| See agents/workflows shared with them; own run history | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Chat, run agents and workflows | | ✓ | ✓ | | ✓ | ✓ |
| Build agents, workflows, triggers, connections | | | ✓ | | ✓ | ✓ |
| See everything in the organization (incl. private items, all runs) | | | | ✓ (read-only) | ✓ | ✓ |
| Audit log, monitoring | | | | ✓ | ✓ (own org) | ✓ (all orgs) |
| Manage users | | | | | ✓ (own org) | ✓ (all orgs) |
| Edit anyone's agents/workflows in the organization | | | | | ✓ | ✓ |
| LLM models, platform settings, organizations | | | | | | ✓ |

Definitions: `backend/app/rbac.py` (`ROLE_PERMISSIONS`). Escalation rules
(`backend/app/routers/users.py`):

- Only a platform admin can grant `platform_admin` or change a platform admin.
- Org admins manage users in their own organization only and cannot create users elsewhere.
- The last active admin of an organization, and the last platform admin, cannot be demoted or
  deactivated.
- Role or deactivation changes end all of that user's sessions at once.
- No request can set its own role. Sign-in bodies and query parameters are ignored, and the role
  is read from the database on every request.

## Sign-in and sessions

- **Passwords:**
  - bcrypt hashing; at least 12 characters with three character classes.
  - Constant-time handling of unknown emails.
  - Lockout after repeated failures, plus a per-address failure limit.
- **Sessions:**
  - Signing in creates a server-side session (`auth_sessions`).
  - The browser receives a **15-minute access token** (`JWT_EXPIRE_MINUTES`, at most 60 in
    production). It is HS256-signed and includes issuer, audience, `sid`, `nbf`, `exp` and a
    token version.
  - The browser also receives an **HttpOnly, SameSite=Strict, Secure refresh cookie**, scoped to
    `/api/auth`.
  - `POST /api/auth/refresh` rotates the refresh token on every use. Presenting an old refresh
    token again revokes the whole session and is audited as `auth.refresh_reuse`. Sessions end
    after `REFRESH_EXPIRE_HOURS` (default 12) at the latest.
- **Revocation:**
  - Each request checks the session, user, organization and token version against the database.
  - `POST /api/auth/logout` ends the current session; `POST /api/auth/logout-all` ends every
    session of the user.
  - A password change or reset, a role change or a deactivation ends all of the user's sessions.
- **Secrets:**
  - `JWT_SECRET` has no built-in fallback.
  - In development an unset secret becomes a random value per process, so sessions end on restart.
  - Production refuses to start unless the secret has at least 32 characters.

### Microsoft Entra ID (OIDC)

- **Flow:** authorization code flow with PKCE, `state` (in a signed, HttpOnly, 10-minute cookie)
  and `nonce`.
- **ID token checks:**
  - The signature is checked against Microsoft's published keys (JWKS).
  - The issuer must be your tenant.
  - The audience must be your app.
  - `tid` must match.
  - Expiry is checked.
- **Tokens:** the browser never sees an IdP token or one of ours in a URL. After the callback it
  holds only the refresh cookie and calls `/api/auth/refresh`.
- **Roles:**
  - Roles come from `OIDC_ROLE_MAP`, which maps Entra **app roles** or **group object ids** to
    Star Dust roles; the highest match wins.
  - `platform_admin` can never be granted this way, and a platform admin's role is never changed
    by sign-in.
  - An existing account (matched by Entra object id, or else email) keeps its role when nothing
    maps.
  - A first-time user without a mapped role gets `OIDC_DEFAULT_ROLE` (viewer, operator or
    developer only). If that is empty, sign-in is refused (`not_provisioned`).
- When the settings are not all present, `/api/auth/oidc/*` returns 404. Nothing ever issues a
  token without verifying the user.
- `LOCAL_LOGIN_ENABLED=false` makes Microsoft the only sign-in. Platform admins keep password
  sign-in as a break-glass path.

**Setup:**
1. In Entra ID, open *App registrations*, then *New registration*, and add a **Web** redirect URI:
   `https://<your host>/api/auth/oidc/callback`.
2. Under *Certificates & secrets*, create a client secret.
3. Optionally define *App roles*, e.g. `StarDust.Developer`, and assign users or groups to them.
4. Set the following:

   | Setting | Value |
   |---|---|
   | `OIDC_TENANT_ID` | Directory (tenant) ID |
   | `OIDC_CLIENT_ID` | Application (client) ID |
   | `OIDC_CLIENT_SECRET` | Put it in the Secret, not the ConfigMap |
   | `OIDC_REDIRECT_URI` | The redirect URI from step 1 |
   | `OIDC_ROLE_MAP` | e.g. `{"StarDust.Developer":"developer","<group-id>":"org_admin"}` |
   | `OIDC_ORG_SLUG` | Organization for new users; default `default` |
   | `OIDC_ALLOWED_DOMAINS` | Optional |
5. Allow outbound HTTPS from the API pods to `login.microsoftonline.com`.

## Requests, secrets and logging

- **Security headers:** every API response sends `nosniff`, `X-Frame-Options: DENY`,
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, `no-store`,
  `Referrer-Policy`, COOP/CORP and `Permissions-Policy`, plus HSTS in production. The web image's
  nginx adds a strict CSP for the app.
- **CORS:** explicit origins only (`*` is refused in production) and no credentials.
- **Rate limits:**
  - Sign-in, refresh and Microsoft sign-in: `AUTH_REQUESTS_PER_MINUTE` per address, per pod.
  - Failed sign-ins: also limited per address per 10 minutes.
  - Runs and chat: per user, per minute, plus a concurrent-run cap.
  - AI drafts: limited per user.
  - Public form links and webhooks: `PUBLIC_REQUESTS_PER_MINUTE` per address, per pod, plus a
    per-trigger cap on form submissions.
- **Request limits:** request bodies over `MAX_REQUEST_BYTES` are refused (413); webhooks are
  capped at 256 kB.
- **Request IDs:** client-supplied request ids are accepted only if short and plain.
- **Validation:** request schemas are validated with Pydantic, including length limits and enums
  for roles and visibility.
- **Saved credentials:**
  - Connections are encrypted at rest (Fernet, `CREDENTIALS_KEY`).
  - API responses never return secret fields.
  - LLM keys come only from `LLM_KEY_*` environment variables.
  - Secret-looking keys are masked in recorded step inputs.
- **Logging:**
  - Logs never include query strings or bodies.
  - A redaction filter removes bearer tokens, JWTs, webhook, form and refresh tokens, and
    `password=`/`api_key=`/`token=` values from every log line and traceback.
  - Webhook, form and refresh tokens are stored only as SHA-256 hashes.
- **Audited events:**
  - sign-in success and failure
  - Microsoft sign-in
  - refresh-token reuse
  - logout and logout-all
  - password changes and resets
  - user create, update and role change; role sync from Entra
  - organization create and update
  - every create, update, delete and run of agents, workflows, triggers and connections
  - settings changes
