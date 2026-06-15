# Supabase Auth setup (task 2.9)

How to provision the Supabase project HexCrawl authenticates against, and how the
backend consumes it. This is a **runbook** — the console steps are performed once,
by hand, in the Supabase dashboard; the repo only carries the configuration the
backend needs to *verify* tokens.

## Where auth lives in the architecture

The backend is a **stateless resource server**. It never logs users in, never holds a
session, and never sees a refresh token. The frontend owns the Supabase JS SDK and the
login / refresh-token flow (QUESTIONS.md Phase 2). The backend's only job is to *verify*
the access-token JWT on each request and read the user id (`sub`) from its claims.

Verification is **asymmetric (JWKS)**: Supabase signs access tokens with a private key
(RS256/ES256) and publishes the matching public keys at a JWKS endpoint. The backend
fetches those public keys and verifies signatures — there is **no shared secret** on the
backend. The actual verification dependency (`get_current_user`) is built in task 2.10;
this task only wires the config it reads.

## One-time console steps

1. Create a Supabase project (free tier is fine) at <https://supabase.com/dashboard>.
   Game Postgres + Redis stay **local** in `docker-compose`; only Auth (and later
   Storage, task 2.11) come from the cloud project.
2. **Authentication → Providers → Email**: enable it. Decide whether to require email
   confirmation for sign-up (recommended on) — this is a frontend-flow concern, but set
   the policy here now.
3. **Authentication → URL Configuration**: add the local frontend origin
   (`http://localhost:5173`) to the redirect allow-list so the SDK can complete logins
   in dev. The production origin is added later (open question, task 3.4).

## Keys and values to copy into `.env`

From **Project Settings → API**:

| Dashboard field            | `.env` var                   | Notes |
|----------------------------|------------------------------|-------|
| Project URL                | `SUPABASE_URL`               | e.g. `https://<ref>.supabase.co`. Issuer and JWKS URL are derived from this. |
| Project API key — `anon`   | `SUPABASE_ANON_KEY`          | **Public/safe for the browser.** RLS-scoped. |
| Project API key — `service_role` | `SUPABASE_SERVICE_ROLE_KEY` | **Secret. Bypasses Row-Level Security — never ship to the browser or commit it.** Backend-only, for privileged server-side calls. |

`SUPABASE_JWT_AUDIENCE` defaults to `authenticated` (the `aud` claim Supabase sets for a
logged-in user) — override only if your project differs. Copy `.env.example` → `.env` and
fill the three Supabase values above.

## The verification contract (what task 2.10 will enforce)

Derived by `Settings` from `SUPABASE_URL` (see `src/config.py`):

- **JWKS URL** — `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` (`Settings.supabase_jwks_url`)
- **Issuer (`iss`)** — `{SUPABASE_URL}/auth/v1` (`Settings.supabase_issuer`)
- **Audience (`aud`)** — `authenticated` (`Settings.supabase_jwt_audience`)

The minimum bar for accepting a token (task 2.10):

1. **Verify the signature** against the JWKS public key matched by the token's `kid`.
2. **Pin the algorithm** to the asymmetric family the project uses (RS256/ES256) and
   **reject `alg: none`** — accepting an unsigned/`none` token, or letting the attacker
   choose the algorithm, is the classic JWT bypass.
3. **Check `exp`** (and `nbf`/`iat`) — expired tokens are rejected; the client refreshes
   via the Supabase SDK once `exp` passes.
4. **Check `aud` and `iss`** — so a token minted for another service (or another Supabase
   project) cannot be replayed against this API.

Any failure → `401 Unauthorized` (with a `WWW-Authenticate` header). Authorisation
(ownership — "is this *your* game?") is **not** done here; it lives next to the resource
in the use case (authN at the edge, authZ next to the data).

## Security notes

- `service_role` leaking is a full-database compromise — it bypasses RLS entirely. Keep it
  out of the frontend bundle, logs, and version control.
- A JWT is **signed, not encrypted** — its claims are readable by anyone (base64url). Never
  put secrets in custom claims; trust comes from the signature, not from secrecy.
