/**
 * The auth screens (task 5.11): login / register over Supabase email+password.
 *
 * One component, three top-level views keyed off the auth store — `loading`
 * (session restore in flight), signed-in (email + sign out), and the form.
 * The form's own submit lifecycle is the explicit `AuthSubmitState` union, so
 * every request state renders (submitting, error-with-copy, check-your-email)
 * and the happy path can't be the only path (5.10 doctrine).
 *
 * There is no "logged in!" success state here: a successful login lands via
 * the SDK's SIGNED_IN event → `useAuthListener` → the store, and this screen
 * simply re-renders into its signed-in view. Auth state has one source of
 * truth; the form never mirrors it locally.
 *
 * All state resets happen in event handlers (mode switch, submit), never in
 * effects — the same `set-state-in-effect` rule the leaderboard hook works
 * under. Client-side validation is UX only; Supabase re-validates, and the
 * backend independently verifies every JWT (the real boundary).
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthStore } from "./authStore";
import { getSupabase } from "./supabaseClient";
import {
  AUTH_MODE_TABS,
  authErrorMessage,
  submitLabel,
  validateCredentials,
  type AuthMode,
  type AuthSubmitState,
} from "./authModel";

const inputClass =
  "w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 " +
  "text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none";

function SignedInPanel() {
  const session = useAuthStore((s) => s.session);

  return (
    <div data-testid="auth-signed-in" className="space-y-4">
      <p className="text-slate-300">
        Signed in as{" "}
        <span className="font-mono text-emerald-400">
          {session?.user.email}
        </span>
      </p>
      <div className="flex items-center gap-4">
        <Link
          to="/"
          className="rounded bg-emerald-600 px-4 py-1.5 font-semibold text-white hover:bg-emerald-500"
        >
          Back to game
        </Link>
        <button
          type="button"
          onClick={() => void getSupabase().auth.signOut()}
          className="rounded bg-slate-700 px-4 py-1.5 font-semibold text-slate-100 hover:bg-slate-600"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

function AuthForm() {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submit, setSubmit] = useState<AuthSubmitState>({ status: "idle" });

  const switchMode = (next: AuthMode) => {
    setMode(next);
    // A stale error/confirmation banner from the other mode would mislead.
    setSubmit({ status: "idle" });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (submit.status === "submitting") return; // double-submit guard

    const problem = validateCredentials(email, password);
    if (problem !== null) {
      setSubmit({ status: "error", message: problem });
      return;
    }

    setSubmit({ status: "submitting" });
    const auth = getSupabase().auth;

    if (mode === "login") {
      const { error } = await auth.signInWithPassword({ email, password });
      // Success needs no local state: SIGNED_IN flows through the listener
      // and this whole form unmounts in favour of the signed-in panel.
      setSubmit(
        error !== null
          ? { status: "error", message: authErrorMessage(error) }
          : { status: "idle" },
      );
      return;
    }

    const { data, error } = await auth.signUp({ email, password });
    if (error !== null) {
      setSubmit({ status: "error", message: authErrorMessage(error) });
      return;
    }
    // With email confirmation on (the project default), sign-up returns a
    // user but no session — the account exists, the player must click the
    // emailed link before login works. With confirmation off, a session
    // arrives and the listener signs the player straight in.
    setSubmit(
      data.session === null
        ? { status: "needs_confirmation", email }
        : { status: "idle" },
    );
  };

  return (
    <div className="max-w-sm space-y-4">
      <div role="group" aria-label="Auth mode" className="flex gap-2">
        {AUTH_MODE_TABS.map((tab) => {
          const active = tab.mode === mode;
          return (
            <button
              key={tab.mode}
              type="button"
              aria-pressed={active}
              onClick={() => switchMode(tab.mode)}
              className={`rounded px-4 py-1.5 font-semibold ${
                active
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-800 text-slate-300 hover:text-white"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {submit.status === "needs_confirmation" ? (
        <p data-testid="auth-needs-confirmation" className="text-emerald-400">
          Almost there — we sent a confirmation link to{" "}
          <span className="font-mono">{submit.email}</span>. Click it, then log
          in.
        </p>
      ) : (
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-3">
          <label className="block space-y-1">
            <span className="text-sm text-slate-400">Email</span>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm text-slate-400">Password</span>
            <input
              type="password"
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
            />
          </label>

          {submit.status === "error" && (
            <p data-testid="auth-error" className="text-amber-400">
              {submit.message}
            </p>
          )}

          <button
            type="submit"
            data-testid="auth-submit"
            disabled={submit.status === "submitting"}
            className="rounded bg-emerald-600 px-4 py-1.5 font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {submitLabel(mode, submit.status === "submitting")}
          </button>
        </form>
      )}
    </div>
  );
}

export default function AuthScreen() {
  const status = useAuthStore((s) => s.status);

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-bold">Account</h1>
      {status === "loading" ? (
        <p data-testid="auth-loading" className="text-slate-400">
          Checking session…
        </p>
      ) : status === "signed_in" ? (
        <SignedInPanel />
      ) : (
        <AuthForm />
      )}
    </section>
  );
}
