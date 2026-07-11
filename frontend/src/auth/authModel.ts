/**
 * Pure display/validation logic for the auth screens (task 5.11) — the
 * `<x>Model.ts` half of the feature, mirroring `leaderboardModel.ts`:
 * component files export only components (react-refresh rule), so the
 * mode table, form validation, and error mapping live here, unit-testable
 * without a DOM.
 */

/** The two form modes; the screen toggles between them like the 5.10 tabs. */
export type AuthMode = "login" | "register";

export const AUTH_MODE_TABS: ReadonlyArray<{
  mode: AuthMode;
  label: string;
}> = [
  { mode: "login", label: "Login" },
  { mode: "register", label: "Register" },
];

/** Per-mode submit-button copy, in both rest and in-flight states. */
export function submitLabel(mode: AuthMode, submitting: boolean): string {
  if (mode === "login") return submitting ? "Logging in…" : "Login";
  return submitting ? "Creating account…" : "Create account";
}

/**
 * Supabase's default minimum password length. Checked client-side only to
 * fail fast with a friendlier message — the authoritative rejection is
 * Supabase's (client checks are UX, never the boundary).
 */
export const MIN_PASSWORD_LENGTH = 6;

/**
 * Validate the form before hitting the network. Returns the user-facing
 * problem, or `null` when the form is submittable. Deliberately shallow on
 * email (non-empty + an "@"): real deliverability is proven by the
 * confirmation email, and stricter regexes reject valid addresses.
 */
export function validateCredentials(
  email: string,
  password: string,
): string | null {
  if (email.trim() === "" || !email.includes("@")) {
    return "Enter a valid email address.";
  }
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  return null;
}

/**
 * The submit lifecycle of the auth form, one variant per renderable state
 * (the 5.10 discriminated-union doctrine). `needs_confirmation` is
 * register-only: Supabase created the account but holds the session until
 * the emailed link is clicked, so the screen must say so instead of
 * silently staying "signed out". A successful login has no variant here —
 * the SDK fires SIGNED_IN, the listener updates the store, and the screen
 * re-renders into its signed-in view from that single source of truth.
 */
export type AuthSubmitState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "error"; message: string }
  | { status: "needs_confirmation"; email: string };

/**
 * Map a Supabase auth error to user-facing copy. The SDK's `AuthError`
 * messages are already human-readable English ("Invalid login credentials"),
 * so they pass through; the fallback covers network failures and anything
 * without a usable message — never show the player a blank error.
 */
export function authErrorMessage(error: { message?: string } | null): string {
  const message = error?.message?.trim();
  return message !== undefined && message !== ""
    ? message
    : "Something went wrong — try again.";
}
