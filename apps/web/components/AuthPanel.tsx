"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  AuthError,
  pauseSeconds,
  validatePin,
  type AuthRequest,
  type AuthOperation,
} from "@xcode/shared";
import { authApi } from "../lib/api";
import { onSessionExpired, restoreSession } from "../lib/session";
import { PinInput } from "./PinInput";
import { AppShell } from "./AppShell";
import { AuthButton, AuthField, AuthHeading, AuthInput, AuthLayout, CheckRow, DemoBox } from "./authControls";
import { Banner, LinkButton, Skeleton } from "./ui";

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
  const [restoring, setRestoring] = useState(true);
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
  // The PIN that produced the current device challenge, so "Send a new code" can repeat that
  // sign-in instead of submitting an empty PIN (a failed attempt). Never rendered.
  const challengePin = useRef("");

  useEffect(() => {
    let active = true;
    // A page refresh keeps the session cookies: pick the session back up instead of asking
    // for the PIN again. (The cookies only outlive the browser when the device is remembered.)
    void restoreSession().then((signedIn) => {
      if (!active) return;
      if (signedIn) setScreen("authenticated");
      setRestoring(false);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(
    () =>
      onSessionExpired(() => {
        navigate("sign-in");
        setMessage("Your session has ended. Sign in again.");
      }),
    [],
  );

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
    challengePin.current = "";
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
    overrides: Partial<Pick<AuthRequest, "phoneNumber" | "pin" | "code">> = {},
  ) {
    setBusy(true);
    setMessage("");

    try {
      const submittedPhone = overrides.phoneNumber ?? phoneNumber;
      const submittedPin = overrides.pin ?? pin;
      const result = await authApi(operation, {
        phoneNumber: submittedPhone,
        pin: submittedPin,
        code: overrides.code ?? code,
        rememberDevice,
      });
      setDevelopmentCode(result.developmentCode || "");
      setMaskedEmail(result.maskedEmail || "");

      if (result.status === "authenticated") {
        navigate("authenticated");
        setPausedUntil(0);
      } else if (result.status === "verification_required") {
        challengePin.current = submittedPin;
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

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    // Browser autofill can fill fields without an input event React sees. Submit what is on
    // screen and bring state in line, so the next render does not wipe the filled values.
    const fields = new FormData(event.currentTarget);
    const digits = (value: string) => value.replace(/[^0-9]/g, "");
    const field = (name: string, current: string, clean = (value: string) => value) => {
      const value = fields.get(name);
      return typeof value === "string" ? clean(value) : current;
    };
    const submittedPhone = field("phoneNumber", phoneNumber);
    const submittedPin = field("pin", pin, digits);
    const submittedConfirm = field("confirmPin", confirmPin, digits);
    const submittedCode = field("code", code, digits);
    setPhoneNumber(submittedPhone);
    setPin(submittedPin);
    setConfirmPin(submittedConfirm);
    setCode(submittedCode);

    if (screen === "verify-code") {
      if (submittedCode.length === 6 && pinFlow)
        void execute(`${pinFlow}/verify` as AuthOperation, { phoneNumber: submittedPhone, pin: "", code: submittedCode });
      return;
    }

    if (changingPin && requested && validatePin(submittedPin)) {
      setMessage(validatePin(submittedPin)!);
      return;
    }
    if (changingPin && requested && submittedPin !== submittedConfirm) {
      setMessage("The PINs do not match.");
      return;
    }

    const operation = changingPin
      ? (`${screen}/${requested ? "complete" : "request"}` as AuthOperation)
      : (screen as AuthOperation);
    void execute(operation, { phoneNumber: submittedPhone, pin: submittedPin, code: submittedCode });
  }

  if (screen === "authenticated" && !restoring) return <AppShell onSignOut={() => void execute("sign-out")} />;

  const verifying = screen === "verify-device" || screen === "verify-code";
  const title =
    screen === "setup-pin" && requested ? "Choose your PIN" : screen === "pin-reset" && requested ? "Choose a new PIN" : titles[screen];
  const lead =
    screen === "sign-in"
      ? "Use the mobile number your admin registered for you."
      : verifying
        ? `We sent a code to ${maskedEmail || "your registered email"}. It is valid for 10 minutes.`
        : requested
          ? "Your code is confirmed. Choose a new PIN of 4 to 8 digits."
          : "Enter your mobile number. We will send a code to the email address your admin registered for you.";

  return (
    <AuthLayout>
      {restoring ? (
        <section aria-busy="true" aria-labelledby="auth-title" className="flex flex-col gap-4">
          <AuthHeading title="Signing you in" lead="Checking for your session..." />
          <Skeleton className="h-14 rounded-xl" />
          <Skeleton className="h-14 rounded-full" />
        </section>
      ) : (
        <form onSubmit={submit} aria-labelledby="auth-title" className="flex flex-col gap-4">
          <AuthHeading title={title} lead={lead} />

          {!verifying && !requested && (
            <AuthField label="Mobile number" htmlFor="phoneNumber">
              <AuthInput
                id="phoneNumber"
                name="phoneNumber"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="0712 345 678"
                required
                value={phoneNumber}
                onChange={(event) => setPhoneNumber(event.target.value)}
              />
            </AuthField>
          )}

          {(screen === "sign-in" || (changingPin && requested)) && <PinInput value={pin} onChange={setPin} newPin={changingPin} />}

          {changingPin && requested && (
            <AuthField label="Type it again" htmlFor="confirmPin">
              <AuthInput
                digits
                id="confirmPin"
                name="confirmPin"
                type="password"
                inputMode="numeric"
                maxLength={8}
                placeholder="4 to 8 numbers"
                autoComplete="new-password"
                required
                value={confirmPin}
                onChange={(event) => setConfirmPin(event.target.value.replace(/[^0-9]/g, ""))}
                aria-invalid={confirmPin.length > 0 && confirmPin !== pin}
              />
            </AuthField>
          )}

          {verifying && (
            <>
              <AuthField label="6 digit code" htmlFor="code">
                <AuthInput
                  digits
                  id="code"
                  name="code"
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  placeholder="6 numbers"
                  required
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/[^0-9]/g, ""))}
                />
              </AuthField>
              <CheckRow label="Remember this device" checked={rememberDevice} onChange={(event) => setRememberDevice(event.target.checked)} />
            </>
          )}

          {remaining > 0 && screen === "sign-in" && (
            <Banner tone="offline" role="timer">
              Sign-in paused. Try again in {Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}, or reset your PIN.
            </Banner>
          )}
          {message && (!remaining || screen !== "sign-in") && <Banner>{message}</Banner>}

          <AuthButton type="submit" aria-busy={busy || undefined} disabled={busy || (remaining > 0 && screen === "sign-in")}>
            {busy
              ? "Please wait..."
              : changingPin && !requested
                ? "Send code"
                : changingPin && requested
                  ? "Save PIN"
                  : verifying
                    ? "Confirm code"
                    : "Sign in"}
          </AuthButton>

          {remaining > 0 && screen === "sign-in" && (
            <AuthButton tone="outline" disabled={busy} onClick={() => beginPinReset(true)}>
              Reset PIN
            </AuthButton>
          )}

          {screen === "sign-in" ? (
            <div className="flex flex-wrap items-center justify-between gap-1">
              <LinkButton
                align="start"
                disabled={busy}
                onClick={() => {
                  setPinFlow("setup-pin");
                  navigate("setup-pin");
                }}
              >
                First time here?
              </LinkButton>
              <LinkButton align="end" disabled={busy} onClick={() => beginPinReset()}>
                Forgot PIN?
              </LinkButton>
            </div>
          ) : verifying ? (
            <div className="flex flex-wrap items-center justify-between gap-1">
              <LinkButton
                align="start"
                disabled={busy}
                onClick={() => {
                  if (screen === "verify-device") {
                    if (challengePin.current) void execute("sign-in", { pin: challengePin.current });
                    else navigate("sign-in");
                  } else if (pinFlow) void execute(`${pinFlow}/request` as AuthOperation, { pin: "", code: "" });
                }}
              >
                Send a new code
              </LinkButton>
              <LinkButton align="end" disabled={busy} onClick={() => navigate(screen === "verify-code" && pinFlow ? pinFlow : "sign-in")}>
                Cancel
              </LinkButton>
            </div>
          ) : (
            <LinkButton align="start" className="self-start" disabled={busy} onClick={() => navigate("sign-in")}>
              Back to sign in
            </LinkButton>
          )}

          {verifying && (
            <>
              <p className="m-0 text-sm text-grey">No email? Check your spam folder, or ask your admin to confirm your email address.</p>
              {developmentCode && (
                <DemoBox data-demo-code={developmentCode}>
                  Demo only: your code is <strong className="tracking-[0.08em] text-navy">{formattedDevelopmentCode}</strong>
                </DemoBox>
              )}
            </>
          )}

          {/* Demo numbers for development only. A PIN someone chose is never kept or shown. */}
          {screen === "sign-in" && process.env.NODE_ENV !== "production" && (
            <DemoBox help>
              <strong className="text-navy">Demo logins</strong>
              <ul className="mt-1.5 mb-0 list-disc pl-4.5">
                {[
                  ["Owner", "0733 520 614"],
                  ["Revenue clerk", "0712 345 678"],
                  ["Office admin", "0722 410 355"],
                  ["Fleet manager", "0700 111 222"],
                ].map(([label, phone]) => (
                  <li key={phone}>
                    {label}: {phone}
                  </li>
                ))}
              </ul>
            </DemoBox>
          )}
        </form>
      )}
    </AuthLayout>
  );
}
