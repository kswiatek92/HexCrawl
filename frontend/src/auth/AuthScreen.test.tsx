import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AuthScreen from "./AuthScreen";
import { useAuthStore } from "./authStore";
import {
  fakeAuth,
  makeSession,
  resetAuthStore,
  resetFakeAuth,
} from "../test/fakeSupabase";

vi.mock("./supabaseClient", async () => {
  const { fakeSupabase } = await import("../test/fakeSupabase");
  return { getSupabase: () => fakeSupabase };
});

function renderScreen() {
  return render(
    <MemoryRouter>
      <AuthScreen />
    </MemoryRouter>,
  );
}

/** Drive the form; the screen renders it only when signed out. */
async function submitForm(email: string, password: string) {
  const user = userEvent.setup();
  if (email !== "") await user.type(screen.getByLabelText("Email"), email);
  if (password !== "")
    await user.type(screen.getByLabelText("Password"), password);
  // By testid: the mode tab and the submit button can share the name "Login".
  await user.click(screen.getByTestId("auth-submit"));
  return user;
}

beforeEach(() => {
  resetFakeAuth();
  resetAuthStore();
  useAuthStore.getState().setSession(null); // default: signed out, form shows
});

describe("AuthScreen states", () => {
  it("shows the restore placeholder while the session is loading", () => {
    resetAuthStore(); // back to "loading"
    renderScreen();
    expect(screen.getByTestId("auth-loading")).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).toBeNull();
  });

  it("shows the signed-in panel with the account email and sign-out", async () => {
    useAuthStore.getState().setSession(makeSession("k@example.com"));
    renderScreen();

    expect(screen.getByTestId("auth-signed-in")).toHaveTextContent(
      "k@example.com",
    );
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(fakeAuth.signOut).toHaveBeenCalledOnce();
  });
});

describe("login", () => {
  it("submits the typed credentials to signInWithPassword", async () => {
    renderScreen();
    await submitForm("k@example.com", "secret1");

    expect(fakeAuth.signInWithPassword).toHaveBeenCalledWith({
      email: "k@example.com",
      password: "secret1",
    });
    expect(screen.queryByTestId("auth-error")).toBeNull();
  });

  it("surfaces the SDK's error message on a failed login", async () => {
    fakeAuth.signInWithPassword.mockResolvedValue({
      data: {},
      error: { message: "Invalid login credentials" },
    });
    renderScreen();
    await submitForm("k@example.com", "wrong-password");

    expect(await screen.findByTestId("auth-error")).toHaveTextContent(
      "Invalid login credentials",
    );
  });

  it("rejects an invalid form client-side without calling the SDK", async () => {
    renderScreen();
    await submitForm("k@example.com", "short");

    expect(await screen.findByTestId("auth-error")).toHaveTextContent(
      /password/i,
    );
    expect(fakeAuth.signInWithPassword).not.toHaveBeenCalled();
  });
});

describe("register", () => {
  it("signs up and shows check-your-email when confirmation is pending", async () => {
    const user = userEvent.setup();
    renderScreen();
    await user.click(screen.getByRole("button", { name: "Register" }));
    await submitForm("new@example.com", "secret1");

    expect(fakeAuth.signUp).toHaveBeenCalledWith({
      email: "new@example.com",
      password: "secret1",
    });
    expect(
      await screen.findByTestId("auth-needs-confirmation"),
    ).toHaveTextContent("new@example.com");
    // The form is replaced by the banner — no accidental double sign-up.
    expect(screen.queryByLabelText("Email")).toBeNull();
  });

  it("shows no banner when sign-up returns a live session (confirmation off)", async () => {
    fakeAuth.signUp.mockResolvedValue({
      data: { user: {}, session: makeSession("new@example.com") },
      error: null,
    });
    const user = userEvent.setup();
    renderScreen();
    await user.click(screen.getByRole("button", { name: "Register" }));
    await submitForm("new@example.com", "secret1");

    expect(screen.queryByTestId("auth-needs-confirmation")).toBeNull();
  });

  it("surfaces a sign-up error", async () => {
    fakeAuth.signUp.mockResolvedValue({
      data: { user: null, session: null },
      error: { message: "User already registered" },
    });
    const user = userEvent.setup();
    renderScreen();
    await user.click(screen.getByRole("button", { name: "Register" }));
    await submitForm("dup@example.com", "secret1");

    expect(await screen.findByTestId("auth-error")).toHaveTextContent(
      "User already registered",
    );
  });
});

describe("mode switching", () => {
  it("clears a stale error when switching modes", async () => {
    renderScreen();
    // Short password, not a bad email: `type="email"` native constraint
    // validation blocks the submit before our handler could even run.
    await submitForm("k@example.com", "short");
    expect(await screen.findByTestId("auth-error")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(screen.queryByTestId("auth-error")).toBeNull();
  });

  it("marks the active mode with aria-pressed", async () => {
    renderScreen();
    // `pressed` filters to the tabs — the submit button carries no aria-pressed.
    const login = screen.getByRole("button", { name: "Login", pressed: true });
    const register = screen.getByRole("button", {
      name: "Register",
      pressed: false,
    });

    await userEvent.click(register);
    expect(register).toHaveAttribute("aria-pressed", "true");
    expect(login).toHaveAttribute("aria-pressed", "false");
  });
});
