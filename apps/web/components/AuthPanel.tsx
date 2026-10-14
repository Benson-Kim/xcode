"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { AuthError, type CodePurpose } from "@xcode/shared/auth";
import { formatPhone, initials, normalisePhone } from "@xcode/shared/format";

import { authApi, readDevice } from "../lib/api";
import { SecurityCheckError } from "../lib/checkedFetch";
import { useResource } from "../lib/data";
import { onSessionExpired, readSession, restoreSession } from "../lib/session";
import { AppShell } from "./AppShell";
import { Brand } from "./Brand";
import { Skeleton } from "./ui";

// Steps: phone, then pin when the person has one, code when the device is new, at first sign in or for a reset,
// and newpin after a first sign in or reset code. A trusted device that remembers its person starts at pin with
// the name shown (XCODE Web v2.33).
type Step = "phone" | "pin" | "code" | "newpin";

type Known = { firstName: string; lastName: string; role: string };

const DEFAULT_IDLE_SECONDS = 900;
const ACTIVITY = ["pointerdown", "keydown", "touchstart", "wheel"] as const;

const titles: Record<CodePurpose, string> = {
  new_device: "Confirm this device",
  first_setup: "First sign in",
  pin_reset: "Reset PIN",
};

const tries = (left: number | null | undefined, what: string) =>
  typeof left === "number"
    ? `Wrong ${what}. ${left} ${left === 1 ? "try" : "tries"} left.`
    : what === "PIN"
      ? "Wrong PIN."
      : "That code has expired. Send a new one.";

// Asks for the PIN again after a while without activity, so a screen left open does not stay open.
function useIdleLock(enabled: boolean, seconds: number, onIdle: () => void) {
  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(onIdle, seconds * 1000);
    };
    arm();
    for (const event of ACTIVITY)
      window.addEventListener(event, arm, { passive: true });
    return () => {
      clearTimeout(timer);
      for (const event of ACTIVITY) window.removeEventListener(event, arm);
    };
  }, [enabled, seconds, onIdle]);
}

export function AuthPanel() {
  const [restoring, setRestoring] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  // The PIN is asked again over the app after a while without activity; what was typed stays underneath.
  const [locked, setLocked] = useState(false);
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [known, setKnown] = useState<Known | null>(null);
  const [pinLocked, setPinLocked] = useState(false);
  const [purpose, setPurpose] = useState<CodePurpose>("new_device");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [trust, setTrust] = useState(true);
  const [message, setMessage] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [developmentCode, setDevelopmentCode] = useState("");
  const [pin, setPin] = useState("");
  const [code, setCode] = useState("");
  const [newPin, setNewPin] = useState("");
  const [repeatPin, setRepeatPin] = useState("");
  // The code that was confirmed, sent again with the new PIN.
  const verifiedCode = useRef("");

  const appearance = useResource<{ idleUnlockSeconds?: number }>(
    signedIn ? "setup/appearance" : null,
  );
  const idleSeconds =
    appearance.data?.idleUnlockSeconds && appearance.data.idleUnlockSeconds > 0
      ? appearance.data.idleUnlockSeconds
      : DEFAULT_IDLE_SECONDS;

  // Where sign-in starts: a trusted device remembers its person and asks for the PIN only.
  const startDevice = useCallback(async (keepPhone = "") => {
    const device = await readDevice();
    setMessage("");
    setNote("");
    setPin("");
    setPinLocked(false);
    if (device.trusted && device.phoneNumber) {
      setPhone(device.phoneNumber);
      setKnown({
        firstName: device.firstName ?? "",
        lastName: device.lastName ?? "",
        role: device.role ?? "",
      });
      setStep("pin");
    } else if (keepPhone) {
      setPhone(keepPhone);
      setKnown(null);
      setStep("pin");
    } else {
      setPhone("");
      setKnown(null);
      setStep("phone");
    }
  }, []);

  useEffect(() => {
    let active = true;
    // A page refresh keeps the session cookies: pick the session back up instead of asking for the PIN again.
    void restoreSession().then(async (open) => {
      if (!active) return;
      if (open) setSignedIn(true);
      else await startDevice();
      if (active) setRestoring(false);
    });
    return () => {
      active = false;
    };
  }, [startDevice]);

  useEffect(
    () =>
      onSessionExpired(() => {
        setSignedIn(false);
        setLocked(false);
        void startDevice().then(() =>
          setMessage("Your session has ended. Sign in again."),
        );
      }),
    [startDevice],
  );

  const lock = useCallback(() => {
    void readSession().then(async (person) => {
      // Work typed but not sent is kept underneath while the PIN is asked for again. Without a number to ask it for
      // (a session restored on a device that is not trusted), the sign-in starts over.
      const device = await readDevice();
      const number = device.phoneNumber || phone;
      if (!number) {
        setSignedIn(false);
        await startDevice();
        return;
      }
      setPhone(number);
      setKnown(
        person ??
          (device.trusted
            ? {
                firstName: device.firstName ?? "",
                lastName: device.lastName ?? "",
                role: device.role ?? "",
              }
            : null),
      );
      setPin("");
      setMessage("");
      setNote("");
      setPinLocked(false);
      setStep("pin");
      setLocked(true);
    });
  }, [phone, startDevice]);
  useIdleLock(signedIn && !locked, idleSeconds, lock);

  function fail(error: unknown, what: "PIN" | "code") {
    if (error instanceof AuthError) {
      const { status, triesLeft } = error.response;
      if (status === "pin_locked") {
        setPinLocked(true);
        setStep("pin");
        setPin("");
        setMessage(error.message);
      } else if (status === "authentication_failed") {
        setMessage(tries(triesLeft, what));
        if (what === "PIN") setPin("");
        else setCode("");
      } else setMessage(error.message);
    } else if (error instanceof SecurityCheckError) setMessage(error.message);
    else setMessage("Could not reach the service. Please try again.");
  }

  async function run(work: () => Promise<void>, what: "PIN" | "code") {
    if (busy) return;
    setBusy(true);
    setMessage("");
    setNote("");
    try {
      await work();
    } catch (error) {
      fail(error, what);
    } finally {
      setBusy(false);
    }
  }

  function signedInNow() {
    setSignedIn(true);
    setLocked(false);
    setPin("");
    setCode("");
    setNewPin("");
    setRepeatPin("");
    setDevelopmentCode("");
    verifiedCode.current = "";
  }

  function toCode(next: CodePurpose, email?: string | null, demo?: string) {
    setPurpose(next);
    setMaskedEmail(email ?? "");
    setDevelopmentCode(demo ?? "");
    setCode("");
    setStep("code");
  }

  // Mobile number first, alone. The server decides the next step.
  function continueWithNumber() {
    const number = normalisePhone(phone);
    if (!/^0\d{9}$/.test(number))
      return setMessage("Enter your 10 digit mobile number.");
    setPhone(number);
    void run(async () => {
      const result = await authApi("start", { phoneNumber: number });
      if (result.status === "pin_required") {
        setKnown(null);
        setPinLocked(false);
        setPin("");
        setStep("pin");
      } else if (result.status === "verification_required")
        toCode(
          result.purpose ?? "first_setup",
          result.maskedEmail,
          result.developmentCode ?? "",
        );
    }, "PIN");
  }

  function submitPin(value = pin) {
    if (pinLocked) return;
    if (!/^\d{4}$/.test(value)) return setMessage("Enter your 4 digit PIN.");
    void run(async () => {
      const result = await authApi("pin", { phoneNumber: phone, pin: value });
      if (result.status === "authenticated") signedInNow();
      else if (result.status === "verification_required") {
        // The server no longer trusts this device: the name stays off the screen until it does again.
        setKnown(null);
        setLocked(false);
        setSignedIn(false);
        toCode(
          result.purpose ?? "new_device",
          result.maskedEmail,
          result.developmentCode ?? "",
        );
      }
    }, "PIN");
  }

  function submitCode(value = code) {
    const digits = value.replace(/\D/g, "");
    if (digits.length !== 6) return setMessage("Enter the 6 digit code.");
    void run(async () => {
      const result = await authApi("code", {
        phoneNumber: phone,
        purpose,
        code: digits,
        trustDevice: trust,
      });
      if (result.status === "authenticated") signedInNow();
      else if (result.status === "code_verified") {
        verifiedCode.current = digits;
        setNewPin("");
        setRepeatPin("");
        setStep("newpin");
      } else if (result.status === "code_resent") {
        setCode("");
        setDevelopmentCode(result.developmentCode ?? "");
        setMessage("Wrong code. A new code has been sent.");
      }
    }, "code");
  }

  function resend() {
    void run(async () => {
      const result = await authApi("code/resend", {
        phoneNumber: phone,
        purpose,
      });
      setCode("");
      setDevelopmentCode(result.developmentCode ?? "");
      setNote("A new code has been sent.");
    }, "code");
  }

  function forgot() {
    void run(async () => {
      const result = await authApi("pin/forgot", { phoneNumber: phone });
      toCode("pin_reset", result.maskedEmail, result.developmentCode ?? "");
    }, "code");
  }

  function saveNewPin() {
    if (!/^\d{4}$/.test(newPin)) return setMessage("The PIN is 4 digits.");
    if (newPin !== repeatPin) return setMessage("The two PINs do not match.");
    void run(async () => {
      try {
        const result = await authApi("pin/new", {
          phoneNumber: phone,
          purpose,
          code: verifiedCode.current,
          pin: newPin,
          trustDevice: trust,
        });
        if (result.status === "authenticated") signedInNow();
      } catch (error) {
        if (
          error instanceof AuthError &&
          error.response.status === "authentication_failed"
        ) {
          // The code ran out while the PIN was chosen: ask for a fresh one.
          setStep("code");
          setCode("");
          setMessage("That code has expired. Send a new one.");
          return;
        }
        throw error;
      }
    }, "PIN");
  }

  function useAnotherNumber() {
    setPhone("");
    setKnown(null);
    setPin("");
    setCode("");
    setMessage("");
    setNote("");
    setPinLocked(false);
    setStep("phone");
  }

  function back() {
    setCode("");
    setNewPin("");
    setRepeatPin("");
    setMessage("");
    setNote("");
    setStep(known ? "pin" : "phone");
  }

  function signOut() {
    void run(async () => {
      await authApi("sign-out", {});
      setSignedIn(false);
      setLocked(false);
      // On a trusted device, sign out returns to the PIN screen for that person.
      await startDevice();
    }, "PIN");
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step === "phone") continueWithNumber();
    else if (step === "pin") (pinLocked ? forgot : submitPin)();
    else if (step === "code") submitCode();
    else saveNewPin();
  }

  const shell = signedIn && !restoring && <AppShell onSignOut={signOut} />;
  if (signedIn && !locked) return shell;

  const trustBox = (
    <label className="ck">
      <input
        type="checkbox"
        checked={trust}
        onChange={(event) => setTrust(event.target.checked)}
      />
      Trust this device
    </label>
  );
  const feedback = (
    <>
      {message && (
        <div className="ferr" role="alert">
          {message}
        </div>
      )}
      {note && (
        <div className="muted" role="status">
          {note}
        </div>
      )}
    </>
  );
  const formattedDevelopmentCode =
    developmentCode.length === 6
      ? `${developmentCode.slice(0, 3)} ${developmentCode.slice(3)}`
      : developmentCode;

  const form = (
    <form onSubmit={submit} className="box" aria-labelledby="auth-title">
      {step === "phone" && (
        <>
          <h1 id="auth-title">Sign in</h1>
          <div className="f">
            <label htmlFor="siPhone">Mobile number</label>
            <input
              className="inp num"
              id="siPhone"
              name="phoneNumber"
              inputMode="tel"
              autoComplete="tel"
              autoFocus
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </div>
          {feedback}
          <button type="submit" className="btn ok" disabled={busy}>
            Continue
          </button>
        </>
      )}
      {step === "pin" && (
        <>
          {known ? (
            <div className="sihello">
              <span className="av2" aria-hidden="true">
                {initials(known.firstName, known.lastName)}
              </span>
              <div>
                <b id="auth-title">
                  {`${known.firstName} ${known.lastName}`.trim()}
                </b>
                <small>{known.role}</small>
              </div>
            </div>
          ) : (
            <>
              <h1 id="auth-title">Sign in</h1>
              <div className="sito">{formatPhone(phone)}</div>
            </>
          )}
          <div className="f">
            <label htmlFor="siPin">PIN</label>
            <input
              className="inp num pinin"
              id="siPin"
              name="pin"
              type="password"
              inputMode="numeric"
              maxLength={4}
              autoComplete="current-password"
              autoFocus
              disabled={pinLocked}
              value={pin}
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                setPin(digits);
                setMessage("");
                // The PIN field submits itself on the fourth digit.
                if (digits.length === 4) submitPin(digits);
              }}
            />
          </div>
          {feedback}
          {pinLocked ? (
            <button
              type="button"
              className="btn ok"
              disabled={busy}
              onClick={forgot}
            >
              Reset PIN
            </button>
          ) : (
            <button type="submit" className="btn ok" disabled={busy}>
              Sign in
            </button>
          )}
          <div className="silinks">
            {!pinLocked && (
              <button
                type="button"
                className="linkb"
                disabled={busy}
                onClick={forgot}
              >
                Forgot PIN
              </button>
            )}
            <button
              type="button"
              className="linkb"
              disabled={busy}
              onClick={useAnotherNumber}
            >
              Use another number
            </button>
          </div>
        </>
      )}
      {step === "code" && (
        <>
          <h1 id="auth-title">{titles[purpose]}</h1>
          <div className="sito">
            Code sent to <b>{maskedEmail || "your email"}</b>
          </div>
          <div className="f">
            <label htmlFor="siCode">6 digit code</label>
            <input
              className="inp num pinin"
              id="siCode"
              name="code"
              inputMode="numeric"
              maxLength={7}
              autoComplete="one-time-code"
              autoFocus
              value={code}
              onChange={(event) => {
                const digits = event.target.value.replace(/\D/g, "");
                setCode(digits);
                setMessage("");
                // The code field submits itself on the sixth digit.
                if (digits.length === 6) submitCode(digits);
              }}
            />
          </div>
          {purpose === "new_device" && trustBox}
          {feedback}
          <button type="submit" className="btn ok" disabled={busy}>
            Continue
          </button>
          <div className="silinks">
            <button
              type="button"
              className="linkb"
              disabled={busy}
              onClick={resend}
            >
              Send a new code
            </button>
            <button
              type="button"
              className="linkb"
              disabled={busy}
              onClick={back}
            >
              Back
            </button>
          </div>
          {developmentCode && (
            <div data-demo-code={developmentCode} className="hint">
              Demo only: your code is{" "}
              <strong className="num">{formattedDevelopmentCode}</strong>
            </div>
          )}
        </>
      )}
      {step === "newpin" && (
        <>
          <h1 id="auth-title">
            {purpose === "first_setup" ? "Choose your PIN" : "New PIN"}
          </h1>
          <div className="f">
            <label htmlFor="siNew">New PIN</label>
            <input
              className="inp num pinin"
              id="siNew"
              name="newPin"
              type="password"
              inputMode="numeric"
              maxLength={4}
              autoComplete="new-password"
              autoFocus
              value={newPin}
              onChange={(event) =>
                setNewPin(event.target.value.replace(/\D/g, ""))
              }
            />
          </div>
          <div className="f">
            <label htmlFor="siNew2">Repeat PIN</label>
            <input
              className="inp num pinin"
              id="siNew2"
              name="repeatPin"
              type="password"
              inputMode="numeric"
              maxLength={4}
              autoComplete="new-password"
              value={repeatPin}
              onChange={(event) =>
                setRepeatPin(event.target.value.replace(/\D/g, ""))
              }
            />
          </div>
          {trustBox}
          {feedback}
          <button type="submit" className="btn ok" disabled={busy}>
            Save and sign in
          </button>
          <div className="silinks">
            <button
              type="button"
              className="linkb"
              disabled={busy}
              onClick={back}
            >
              Back
            </button>
          </div>
        </>
      )}
    </form>
  );

  const screen = (
    <div className="signin min-h-screen">
      <header className="side">
        <Brand size={46} />
        <div className="cos">XCODE Web v2.33</div>
      </header>
      <main className="formside">
        <div className="box">
          {restoring ? (
            <section
              aria-busy="true"
              aria-labelledby="auth-title"
              className="box"
            >
              <h1 id="auth-title">Signing you in</h1>
              <div className="muted">Checking for your session...</div>
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </section>
          ) : (
            form
          )}
        </div>
      </main>
    </div>
  );

  // Locked: the app stays mounted underneath, with what was typed, and the PIN screen covers it.
  if (locked)
    return (
      <>
        <div aria-hidden="true" inert className="contents">
          {shell}
        </div>
        <div
          className="fixed inset-0 z-50 overflow-auto"
          style={{ background: "var(--shell)" }}
        >
          {screen}
        </div>
      </>
    );
  return screen;
}
