"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  AuthError,
  pauseSeconds,
  validatePin,
  type AuthOperation,
} from "@xcode/shared";
import { authApi } from "../lib/api";
import { PinInput } from "./PinInput";

type Screen =
  | "sign-in"
  | "verify-device"
  | "setup-pin"
  | "pin-reset"
  | "authenticated";

const titles: Record<Screen, string> = {
  "sign-in": "Welcome back",
  "verify-device": "Verify this device",
  "setup-pin": "Set your first PIN",
  "pin-reset": "Reset your PIN",
  authenticated: "You're signed in",
};

export function AuthPanel() {
  const [screen, setScreen] = useState<Screen>("sign-in");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [pin, setPin] = useState("");
  const [code, setCode] = useState("");
  const [requested, setRequested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [pausedUntil, setPausedUntil] = useState(0);
  const [remaining, setRemaining] = useState(0);

  useEffect(() => {
    const tick = () => setRemaining(pauseSeconds(pausedUntil));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [pausedUntil]);

  function navigate(next: Screen) {
    setScreen(next);
    setPin("");
    setCode("");
    setRequested(false);
    setMessage("");
  }

  const changingPin = screen === "setup-pin" || screen === "pin-reset";

  async function execute(operation: AuthOperation | "devices/current/revoke") {
    setBusy(true);
    setMessage("");

    try {
      const result = await authApi(operation, { phoneNumber, pin, code });

      if (result.status === "authenticated") {
        navigate("authenticated");
        setPausedUntil(0);
      } else if (result.status === "verification_required") {
        navigate("verify-device");
        setMessage(
          "Enter the six-digit code sent to your email. It is valid for 10 minutes.",
        );
      } else if (result.status === "check_email") {
        setRequested(true);
        setMessage(
          "If this account is eligible, a code has been sent. Check your email.",
        );
      } else if (
        result.status === "signed_out" ||
        result.status === "device_revoked"
      )
        navigate("sign-in");
    } catch (error) {
      if (error instanceof AuthError) {
        if (error.response.retryAfterSeconds)
          setPausedUntil(Date.now() + error.response.retryAfterSeconds * 1000);
        setMessage(error.message);
      } else setMessage("Could not reach the service. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();

    if (changingPin && requested && validatePin(pin)) {
      setMessage(validatePin(pin)!);
      return;
    }

    const operation = changingPin
      ? (`${screen}/${requested ? "complete" : "request"}` as AuthOperation)
      : (screen as AuthOperation);
    void execute(operation);
  }

  return (
    <section
      className="w-full max-w-md rounded-2xl bg-white p-8 shadow-lg space-y-6"
      aria-labelledby="auth-title"
    >
      <div>
        <p className="text-sm font-semibold uppercase tracking-widest text-sky-700">
          XCODE
        </p>
        <h1 id="auth-title" className="mt-2 text-3xl font-bold">
          {titles[screen]}
        </h1>
      </div>
      {screen === "authenticated" ? (
        <div className="space-y-4">
          <p>
            Your session is protected with secure, HttpOnly cookies. This
            browser is now trusted.
          </p>
          <button
            disabled={busy}
            className="block underline"
            onClick={() => void execute("refresh")}
          >
            Refresh session
          </button>
          <button
            disabled={busy}
            className="block underline"
            onClick={() => void execute("devices/current/revoke")}
          >
            Revoke trust for this browser
          </button>
          <button
            disabled={busy}
            className="block underline"
            onClick={() => void execute("sign-out")}
          >
            Sign out
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label htmlFor="phoneNumber" className="block font-medium mb-2">
              Mobile number
            </label>
            <input
              id="phoneNumber"
              type="tel"
              autoComplete="phoneNumber"
              required
              value={phoneNumber}
              readOnly={screen === "verify-device" || requested}
              onChange={(e) => setPhoneNumber(e.target.value)}
            />
          </div>

          {(screen === "sign-in" || (changingPin && requested)) && (
            <PinInput value={pin} onChange={setPin} newPin={changingPin} />
          )}

          {(screen === "verify-device" || requested) && (
            <div>
              <label htmlFor="code" className="block font-medium mb-2">
                Email verification code
              </label>
              <input
                id="code"
                autoComplete="one-time-code"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ""))}
              />
            </div>
          )}

          {remaining > 0 && (
            <p role="timer" className="text-amber-800">
              Sign-in paused. Try again in {Math.floor(remaining / 60)}:
              {String(remaining % 60).padStart(2, "0")}, or reset your PIN.
            </p>
          )}

          <button
            className="w-full rounded-lg bg-sky-800 py-3 font-semibold text-white"
            disabled={busy || (remaining > 0 && screen === "sign-in")}
            type="submit"
          >
            {busy
              ? "Please wait…"
              : changingPin && !requested
                ? "Send verification code"
                : screen === "sign-in"
                  ? "Sign in"
                  : "Verify and continue"}
          </button>

          {changingPin && requested && (
            <button
              className="underline text-sm"
              type="button"
              disabled={busy}
              onClick={() => void execute(`${screen}/request`)}
            >
              Resend code (once per minute)
            </button>
          )}
        </form>
      )}

      {message && (
        <p role="status" className="rounded-lg bg-slate-100 p-3 text-sm">
          {message}
        </p>
      )}

      {screen !== "authenticated" && (
        <nav
          className="flex flex-wrap gap-4 text-sm text-sky-800"
          aria-label="Authentication options"
        >
          {screen !== "sign-in" && (
            <button disabled={busy} onClick={() => navigate("sign-in")}>
              Back to sign in
            </button>
          )}

          {screen !== "setup-pin" && (
            <button disabled={busy} onClick={() => navigate("setup-pin")}>
              First time? Set up PIN
            </button>
          )}

          {screen !== "pin-reset" && (
            <button disabled={busy} onClick={() => navigate("pin-reset")}>
              Forgot PIN?
            </button>
          )}
        </nav>
      )}
    </section>
  );
}
