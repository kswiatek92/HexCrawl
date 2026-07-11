import { describe, expect, it } from "vitest";
import {
  AUTH_MODE_TABS,
  MIN_PASSWORD_LENGTH,
  authErrorMessage,
  submitLabel,
  validateCredentials,
} from "./authModel";

describe("AUTH_MODE_TABS", () => {
  it("offers exactly login and register, login first", () => {
    expect(AUTH_MODE_TABS.map((t) => t.mode)).toEqual(["login", "register"]);
  });
});

describe("submitLabel", () => {
  it("names the action per mode", () => {
    expect(submitLabel("login", false)).toBe("Login");
    expect(submitLabel("register", false)).toBe("Create account");
  });

  it("switches to in-flight copy while submitting", () => {
    expect(submitLabel("login", true)).toBe("Logging in…");
    expect(submitLabel("register", true)).toBe("Creating account…");
  });
});

describe("validateCredentials", () => {
  it("accepts a plausible email and a long-enough password", () => {
    expect(validateCredentials("a@b.c", "secret1")).toBeNull();
  });

  it("rejects a blank or @-less email", () => {
    expect(validateCredentials("", "secret1")).toMatch(/email/i);
    expect(validateCredentials("   ", "secret1")).toMatch(/email/i);
    expect(validateCredentials("not-an-email", "secret1")).toMatch(/email/i);
  });

  it("rejects a password below the Supabase minimum", () => {
    const short = "x".repeat(MIN_PASSWORD_LENGTH - 1);
    expect(validateCredentials("a@b.c", short)).toMatch(/password/i);
  });

  it("accepts a password exactly at the minimum (boundary)", () => {
    const exact = "x".repeat(MIN_PASSWORD_LENGTH);
    expect(validateCredentials("a@b.c", exact)).toBeNull();
  });
});

describe("authErrorMessage", () => {
  it("passes through the SDK's human-readable message", () => {
    expect(authErrorMessage({ message: "Invalid login credentials" })).toBe(
      "Invalid login credentials",
    );
  });

  it("falls back when the error is null, blank, or messageless", () => {
    const fallback = authErrorMessage(null);
    expect(fallback).not.toBe("");
    expect(authErrorMessage({})).toBe(fallback);
    expect(authErrorMessage({ message: "   " })).toBe(fallback);
  });
});
