"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  AuthError,
  pauseSeconds,
  validatePin,
  type AuthRequest,
  type AuthOperation,
} from "@xcode/shared";
import { authApi } from "../lib/api";
import { PinInput } from "./PinInput";
import { AppShell } from "./AppShell";

type Screen =
  | "sign-in"
  | "verify-device"
  | "verify-code"
  | "setup-pin"
  | "pin-reset"
  | "authenticated";

const titles: Record<Screen, string> = {
  "sign-in": "Sign in",
  "verify-device": "Check your email",
  "verify-code": "Check your email",
  "setup-pin": "Set up your PIN",
  "pin-reset": "Reset your PIN",
  authenticated: "You’re signed in",
};

export function AuthPanel() {
  const [screen, setScreen] = useState<Screen>("sign-in");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [code, setCode] = useState("");
  const [requested, setRequested] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [developmentCode, setDevelopmentCode] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [pausedUntil, setPausedUntil] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [rememberDevice, setRememberDevice] = useState(false);
  const [pinFlow, setPinFlow] = useState<"setup-pin" | "pin-reset" | null>(
    null,
  );
  const [livePins, setLivePins] = useState<Record<string, string>>({});

  useEffect(() => {
    const tick = () => setRemaining(pauseSeconds(pausedUntil));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [pausedUntil]);

  function navigate(next: Screen) {
    setScreen(next);
    setPin("");
    setConfirmPin("");
    setCode("");
    setRequested(false);
    setMessage("");
    setDevelopmentCode("");
    setMaskedEmail("");
    if (next === "sign-in" || next === "authenticated") setPinFlow(null);
  }

  function beginPinReset(requestCode = false) {
    setPinFlow("pin-reset");
    setScreen("pin-reset");
    setPausedUntil(0);
    setRemaining(0);
    setPin("");
    setConfirmPin("");
    setCode("");
    setRequested(false);
    setMessage("");
    setDevelopmentCode("");
    if (requestCode) void execute("pin-reset/request", { pin: "", code: "" });
  }

  const formattedDevelopmentCode =
    developmentCode.length === 6
      ? `${developmentCode.slice(0, 3)} ${developmentCode.slice(3)}`
      : developmentCode;

  const changingPin = screen === "setup-pin" || screen === "pin-reset";

  async function execute(
    operation: AuthOperation | "devices/current/revoke",
    overrides: Partial<Pick<AuthRequest, "pin" | "code">> = {},
  ) {
    setBusy(true);
    setMessage("");

    try {
      const result = await authApi(operation, {
        phoneNumber,
        pin: overrides.pin ?? pin,
        code: overrides.code ?? code,
      });
      setDevelopmentCode(result.developmentCode || "");
      setMaskedEmail(result.maskedEmail || "");

      if (result.status === "authenticated") {
        if (changingPin && pin)
          setLivePins((current) => ({ ...current, [phoneNumber]: pin }));
        navigate("authenticated");
        setPausedUntil(0);
      } else if (result.status === "verification_required") {
        setDevelopmentCode(result.developmentCode || "");
        setCode("");
        setScreen("verify-device");
        setPin("");
        setConfirmPin("");
        setRequested(false);
        setMessage("");
      } else if (result.status === "check_email") {
        setCode("");
        setRequested(true);
        setScreen("verify-code");
      } else if (result.status === "code_verified" && pinFlow) {
        setRequested(true);
        setScreen(pinFlow);
        setMessage("");
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

    if (screen === "verify-code") {
      if (code.length === 6 && pinFlow)
        void execute(`${pinFlow}/verify` as AuthOperation, { pin: "" });
      return;
    }

    if (changingPin && requested && validatePin(pin)) {
      setMessage(validatePin(pin)!);
      return;
    }
    if (changingPin && requested && pin !== confirmPin) {
      setMessage("The PINs do not match.");
      return;
    }

    const operation = changingPin
      ? (`${screen}/${requested ? "complete" : "request"}` as AuthOperation)
      : (screen as AuthOperation);
    void execute(operation);
  }

  return (
    <section
      className={
        screen === "authenticated" ? "auth-panel auth-panel-app" : "auth-panel"
      }
      aria-labelledby="auth-title"
    >
      {screen === "authenticated" ? (
        <AppShell onSignOut={() => void execute("sign-out")} />
      ) : (
        <div className="auth-heading">
          <h1 id="auth-title">
            {screen === "setup-pin" && requested
              ? "Choose your PIN"
              : screen === "pin-reset" && requested
                ? "Choose a new PIN"
                : titles[screen]}
          </h1>
          <p className="lead">
            {screen === "sign-in"
              ? "Use the mobile number your admin registered for you."
              : screen === "verify-device" || screen === "verify-code"
                ? `We sent a code to ${maskedEmail || "your registered email"}. It is valid for 10 minutes.`
                : requested
                  ? "Your code is confirmed. Choose a new four-digit PIN."
                  : "Enter your mobile number. We will send a code to the email address your admin registered for you."}
          </p>
        </div>
      )}
      {screen !== "authenticated" && (
        <form onSubmit={submit} className="auth-form">
          {screen !== "verify-device" &&
            screen !== "verify-code" &&
            !requested && (
              <div className="field">
                <label htmlFor="phoneNumber">Mobile number</label>
                <input
                  className="input"
                  id="phoneNumber"
                  type="tel"
                  autoComplete="tel"
                  required
                  value={phoneNumber}
                  readOnly={requested}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                />
              </div>
            )}

          {screen === "sign-in" || (changingPin && requested) ? (
            <PinInput value={pin} onChange={setPin} newPin={changingPin} />
          ) : null}

          {changingPin && requested && (
            <div className="field">
              <label htmlFor="confirmPin">Type it again</label>
              <input
                className="input digits"
                id="confirmPin"
                type="password"
                inputMode="numeric"
                maxLength={4}
                autoComplete="new-password"
                required
                value={confirmPin}
                onChange={(event) =>
                  setConfirmPin(event.target.value.replace(/[^0-9]/g, ""))
                }
                aria-invalid={confirmPin.length > 0 && confirmPin !== pin}
              />
            </div>
          )}

          {(screen === "verify-device" || screen === "verify-code") && (
            <div className="field">
              <label htmlFor="code">6 digit code</label>
              <input
                className="input digits"
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

          {(screen === "verify-device" || screen === "verify-code") && (
            <label className="check">
              <input
                type="checkbox"
                checked={rememberDevice}
                onChange={(event) => setRememberDevice(event.target.checked)}
              />
              <span>Remember this device</span>
            </label>
          )}

          {remaining > 0 && screen === "sign-in" && (
            <p role="timer" className="banner offline">
              Sign-in paused. Try again in {Math.floor(remaining / 60)}:
              {String(remaining % 60).padStart(2, "0")}, or reset your PIN.
            </p>
          )}

          <button
            className="btn btn-primary"
            disabled={busy || (remaining > 0 && screen === "sign-in")}
            type="submit"
          >
            {busy
              ? "Please wait..."
              : changingPin && !requested
                ? "Send verification code"
                : changingPin && requested
                  ? "Save PIN"
                  : screen === "verify-device" || screen === "verify-code"
                    ? "Confirm code"
                    : screen === "sign-in"
                      ? "Sign in"
                      : "Verify and continue"}
          </button>

          {remaining > 0 && screen === "sign-in" && (
            <button
              className="btn btn-outline"
              type="button"
              disabled={busy}
              onClick={() => beginPinReset(true)}
            >
              Reset PIN
            </button>
          )}

          {(screen === "verify-device" ||
            screen === "verify-code" ||
            (changingPin && requested)) && (
            <button
              className="link-button"
              type="button"
              disabled={busy}
              onClick={() => {
                if (screen === "verify-device") void execute("sign-in");
                else if (pinFlow)
                  void execute(`${pinFlow}/request` as AuthOperation, {
                    pin: "",
                    code: "",
                  });
              }}
            >
              Send a new code
            </button>
          )}

          {(screen === "verify-device" || screen === "verify-code") && (
            <>
              <p className="small">
                No email? Check your spam folder, or ask your admin to confirm
                your email address.
              </p>
              {developmentCode && (
                <p className="demo">
                  Demo only: your code is{" "}
                  <strong>{formattedDevelopmentCode}</strong>
                </p>
              )}
            </>
          )}
        </form>
      )}

      {message && (!remaining || screen !== "sign-in") && (
        <p role="status" className="banner error">
          {message}
        </p>
      )}

      {screen !== "authenticated" && (
        <nav className="auth-links" aria-label="Authentication options">
          {screen !== "sign-in" && (
            <button disabled={busy} onClick={() => navigate("sign-in")}>
              Back to sign in
            </button>
          )}

          {screen !== "setup-pin" && screen !== "verify-code" && (
            <button
              disabled={busy}
              onClick={() => {
                setPinFlow("setup-pin");
                navigate("setup-pin");
              }}
            >
              First time here?
            </button>
          )}

          {screen !== "pin-reset" && (
            <button disabled={busy} onClick={() => beginPinReset()}>
              Forgot PIN?
            </button>
          )}
          {screen === "verify-code" && (
            <button
              disabled={busy}
              onClick={() => navigate(pinFlow || "sign-in")}
            >
              Cancel
            </button>
          )}
        </nav>
      )}
      {screen === "sign-in" && (
        <div className="login-help">
          <strong>Demo logins</strong>
          <ul>
            {[
              ["Owner", "0733 520 614"],
              ["Revenue clerk", "0712 345 678"],
              ["Office admin", "0722 410 355"],
              ["Fleet manager", "0700 111 222"],
            ].map(([label, phone]) => (
              <li key={phone}>
                {label}: {phone},{" "}
                {livePins[phone]
                  ? `PIN ${livePins[phone]}`
                  : "PIN set by the user"}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
