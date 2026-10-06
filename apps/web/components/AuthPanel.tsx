"use client";

import { useEffect, useRef, useState, type SubmitEvent } from "react";

import {
  AuthError,
  pauseSeconds,
  validatePin,
  type AuthOperation,
  type AuthRequest,
} from "@xcode/shared/auth";

import { authApi } from "../lib/api";
import { onSessionExpired, restoreSession } from "../lib/session";
import { AppShell } from "./AppShell";
import { Brand } from "./Brand";
import { PinInput } from "./PinInput";
import {
  Banner,
  Button,
  Field,
  LinkButton,
  PageHeader,
  Skeleton,
  TextInput,
} from "./ui";

type Screen =
  | "sign-in"
  | "verify-device"
  | "verify-code"
  | "setup-pin"
  | "pin-reset"
  | "authenticated";

// A refused sign-in or code says what to check. The server gives the same answer for a wrong PIN and an unknown
// number (so nobody can find which numbers exist), and the same for a wrong and an expired code.
function failureMessage(operation: string, error: AuthError) {
  if (
    error.httpStatus !== 401 ||
    error.response.status !== "authentication_failed"
  )
    return error.message;
  if (operation === "sign-in")
    return "The mobile number or PIN is not right. Check both and try again.";
  if (operation === "verify-device" || operation.endsWith("/verify"))
    return "That code is not right, or it has expired. Check your email, or tap Send a new code.";
  return error.message;
}

const titles: Record<Screen, string> = {
  "sign-in": "Sign in",
  "verify-device": "Check your email",
  "verify-code": "Check your email",
  "setup-pin": "Set up your PIN",
  "pin-reset": "Reset your PIN",
  authenticated: "You're signed in",
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
        setMessage(failureMessage(operation, error));
      } else setMessage("Could not reach the service. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();

    // Browser autofill can fill fields without an input event React sees. Submit what is on
    // screen and bring state in line, so the next render does not wipe the filled values.
    const fields = new FormData(event.currentTarget);
    const digits = (value: string) => value.replace(/[^0-9]/g, "");
    const field = (
      name: string,
      current: string,
      clean = (value: string) => value,
    ) => {
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
        void execute(`${pinFlow}/verify` as AuthOperation, {
          phoneNumber: submittedPhone,
          pin: "",
          code: submittedCode,
        });
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
    void execute(operation, {
      phoneNumber: submittedPhone,
      pin: submittedPin,
      code: submittedCode,
    });
  }

  if (screen === "authenticated" && !restoring)
    return <AppShell onSignOut={() => void execute("sign-out")} />;

  const verifying = screen === "verify-device" || screen === "verify-code";
  const title =
    screen === "setup-pin" && requested
      ? "Choose your PIN"
      : screen === "pin-reset" && requested
        ? "Choose a new PIN"
        : titles[screen];
  const lead =
    screen === "sign-in" ? (
      "Use the mobile number your admin registered for you."
    ) : verifying ? (
      <>
        {screen === "verify-device" ? "New device. " : ""}We sent a code to{" "}
        {maskedEmail ? (
          <strong className="text-navy">{maskedEmail}</strong>
        ) : (
          "your registered email"
        )}
        , the email your admin registered. It works for 10 minutes.
      </>
    ) : requested ? (
      "Your code is confirmed. Choose a new PIN of 4 to 8 digits."
    ) : (
      "Enter your mobile number. We will send a code to the email address your admin registered for you."
    );

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-2.5 px-6 pt-8 min-[720px]:px-12 min-[720px]:pt-7">
        <Brand />
      </header>
      <main className="flex flex-1 flex-col px-6 pt-7 pb-4 min-[720px]:items-center min-[720px]:justify-center min-[720px]:gap-5 min-[720px]:pt-6 min-[720px]:pb-10">
        <div className="w-full min-[720px]:w-110 min-[720px]:rounded-[20px] min-[720px]:border min-[720px]:border-card-line min-[720px]:bg-surface min-[720px]:p-10 min-[720px]:shadow-panel">
          {restoring ? (
            <section
              aria-busy="true"
              aria-labelledby="auth-title"
              className="flex flex-col gap-4"
            >
              <PageHeader
                title="Signing you in"
                description="Checking for your session..."
              />
              <Skeleton className="h-14 rounded-xl" />
              <Skeleton className="h-14 rounded-full" />
            </section>
          ) : (
            <form
              onSubmit={submit}
              aria-labelledby="auth-title"
              className="flex flex-col gap-4"
            >
              <PageHeader title={title} description={lead} />

              {!verifying && !requested && (
                <Field id="phoneNumber" label="Mobile number">
                  <TextInput
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
                </Field>
              )}

              {(screen === "sign-in" || (changingPin && requested)) && (
                <PinInput value={pin} onChange={setPin} newPin={changingPin} />
              )}

              {changingPin && requested && (
                <Field id="confirmPin" label="Type it again">
                  <TextInput
                    className="text-[22px] tracking-[0.4em] placeholder:text-[17px] placeholder:tracking-normal"
                    id="confirmPin"
                    name="confirmPin"
                    type="password"
                    inputMode="numeric"
                    maxLength={8}
                    placeholder="4 to 8 numbers"
                    autoComplete="new-password"
                    required
                    value={confirmPin}
                    onChange={(event) =>
                      setConfirmPin(event.target.value.replace(/[^0-9]/g, ""))
                    }
                    aria-invalid={confirmPin.length > 0 && confirmPin !== pin}
                  />
                </Field>
              )}

              {verifying && (
                <>
                  <Field id="code" label="6 digit code">
                    <TextInput
                      className="text-[22px] tracking-[0.4em] placeholder:text-[17px] placeholder:tracking-normal"
                      id="code"
                      name="code"
                      autoComplete="one-time-code"
                      inputMode="numeric"
                      pattern="[0-9]{6}"
                      maxLength={6}
                      placeholder="6 numbers"
                      required
                      value={code}
                      onChange={(event) =>
                        setCode(event.target.value.replace(/[^0-9]/g, ""))
                      }
                    />
                  </Field>

                  <label className="flex min-h-11 cursor-pointer items-start gap-3 pt-2.5 text-[15px]">
                    <input
                      type="checkbox"
                      checked={rememberDevice}
                      onChange={(event) =>
                        setRememberDevice(event.target.checked)
                      }
                      className="m-0 size-5.5 shrink-0 accent-blue"
                    />
                    <span>
                      Remember this device. Next time you only need your mobile
                      number and PIN.
                    </span>
                  </label>
                </>
              )}

              {remaining > 0 && screen === "sign-in" && (
                <Banner tone="offline" role="timer">
                  Sign-in paused. Try again in {Math.floor(remaining / 60)}:
                  {String(remaining % 60).padStart(2, "0")}, or reset your PIN.
                </Banner>
              )}
              {message && (!remaining || screen !== "sign-in") && (
                <Banner>{message}</Banner>
              )}

              <Button
                type="submit"
                aria-busy={busy || undefined}
                disabled={busy || (remaining > 0 && screen === "sign-in")}
                className="h-14 w-full border-0 px-0 text-[17px] disabled:opacity-55 aria-busy:cursor-progress aria-busy:bg-blue-busy min-[720px]:h-13"
              >
                {busy
                  ? "Please wait..."
                  : changingPin && !requested
                    ? "Send code"
                    : changingPin && requested
                      ? "Save PIN"
                      : verifying
                        ? "Confirm code"
                        : "Sign in"}
              </Button>

              {remaining > 0 && screen === "sign-in" && (
                <Button
                  tone="outline"
                  disabled={busy}
                  onClick={() => beginPinReset(true)}
                  className="h-14 w-full px-0 text-[17px] disabled:opacity-55 min-[720px]:h-13"
                >
                  Reset PIN
                </Button>
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
                  <LinkButton
                    align="end"
                    disabled={busy}
                    onClick={() => beginPinReset()}
                  >
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
                        if (challengePin.current)
                          void execute("sign-in", {
                            pin: challengePin.current,
                          });
                        else navigate("sign-in");
                      } else if (pinFlow)
                        void execute(`${pinFlow}/request` as AuthOperation, {
                          pin: "",
                          code: "",
                        });
                    }}
                  >
                    Send a new code
                  </LinkButton>
                  <LinkButton
                    align="end"
                    disabled={busy}
                    onClick={() =>
                      navigate(
                        screen === "verify-code" && pinFlow
                          ? pinFlow
                          : "sign-in",
                      )
                    }
                  >
                    Cancel
                  </LinkButton>
                </div>
              ) : (
                <LinkButton
                  align="start"
                  className="self-start"
                  disabled={busy}
                  onClick={() => navigate("sign-in")}
                >
                  Back to sign in
                </LinkButton>
              )}

              {verifying && (
                <>
                  <p className="m-0 text-sm text-grey">
                    No email? Check your spam folder, or ask your admin to
                    confirm your email address.
                  </p>
                  {developmentCode && (
                    <div
                      data-demo-code={developmentCode}
                      className="m-0 rounded-xl border border-dashed border-line px-3.5 py-2.5 text-sm text-grey"
                    >
                      Demo only: your code is{" "}
                      <strong className="tracking-[0.08em] text-navy">
                        {formattedDevelopmentCode}
                      </strong>
                    </div>
                  )}
                </>
              )}

              {/* Demo numbers for development only. A PIN someone chose is never kept or shown. */}
              {screen === "sign-in" &&
                process.env.NODE_ENV !== "production" && (
                  <div className="m-0 rounded-xl border border-dashed border-line px-3.5 py-3 text-sm text-grey">
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
                  </div>
                )}
            </form>
          )}
        </div>
        <p className="mt-auto mb-0 pt-6 text-center text-sm text-grey min-[720px]:m-0 min-[720px]:pt-0">
          New here? Your admin adds you with your mobile number and email
          address.
        </p>
        <p className="mt-2 mb-0 text-center text-xs text-grey min-[720px]:hidden">
          XCODE Web v0.9
        </p>
      </main>
      <p className="m-0 hidden px-12 pb-6 text-[13px] text-grey min-[720px]:block">
        Every sign in is recorded against your name. XCODE Web v0.9
      </p>
    </div>
  );
}
