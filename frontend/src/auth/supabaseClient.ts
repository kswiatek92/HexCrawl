/**
 * Supabase client singleton (task 5.12).
 *
 * The frontend owns the whole credential flow — sign-up, login, session
 * persistence, token refresh — via this SDK client; the backend never sees a
 * password or refresh token and only *verifies* the access-token JWT
 * (ADR-0007, docs/auth-setup.md). SDK defaults are kept deliberately:
 * `persistSession: true` (localStorage) so a reload doesn't log the player
 * out, and `autoRefreshToken: true` so the SDK swaps in a fresh access token
 * before `exp` — the trade-off against an in-memory session (smaller XSS
 * blast radius, but every reload signs you out) is logged in DECISIONS.md.
 *
 * Lazy singleton, not a module-level `createClient(...)`: creation throws on
 * missing config, and doing that at import time would crash every module that
 * transitively imports this file — including tests that `vi.mock` it. First
 * *use* fails loud instead (mirrors `Settings._supabase_base_url` backend-side:
 * report the misconfiguration at the earliest meaningful point, never derive
 * garbage from a blank URL).
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

/** The two build-time env vars the client needs (frontend/.env.example). */
export interface SupabaseConfig {
  url: string;
  anonKey: string;
}

/**
 * Validate raw env values into a config, or explain exactly what is missing.
 * Pure and exported for tests; `getSupabase` applies it to `import.meta.env`.
 */
export function resolveSupabaseConfig(env: {
  VITE_SUPABASE_URL?: string;
  VITE_SUPABASE_ANON_KEY?: string;
}): SupabaseConfig {
  const url = env.VITE_SUPABASE_URL?.trim() ?? "";
  const anonKey = env.VITE_SUPABASE_ANON_KEY?.trim() ?? "";
  if (url === "" || anonKey === "") {
    throw new Error(
      "Supabase is not configured: set VITE_SUPABASE_URL and " +
        "VITE_SUPABASE_ANON_KEY in frontend/.env (see frontend/.env.example " +
        "and docs/auth-setup.md).",
    );
  }
  return { url, anonKey };
}

/** The app-wide Supabase client. Throws with a setup hint if unconfigured. */
export function getSupabase(): SupabaseClient {
  if (client === null) {
    const config = resolveSupabaseConfig(import.meta.env);
    client = createClient(config.url, config.anonKey);
  }
  return client;
}
