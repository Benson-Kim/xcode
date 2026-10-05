import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNetworkState } from "expo-network";
import {
  AuthError,
  validatePin,
  type AuthResponse,
} from "@xcode/shared";
import {
  OfflineError,
  authApi,
  forgetThisPhone,
  keepSession,
} from "../lib/api";
import {
  formatPhone,
  maskPhone,
  normalisePhone,
  phoneError,
} from "../lib/phone";
import {
  DEFAULT_PIN_POLICY,
  OFFLINE_UNLOCK_HOURS,
  loadOfflineTries,
  matchesPinCheck,
  offlineUnlockUntil,
  saveOfflineTries,
  savePinCheck,
  type StoredPerson,
} from "../lib/storage";
import { fetchPerson, initials } from "../session";
import { LinkButton } from "../ui";
import { AuthLayout, type BrandInfo } from "./AuthLayout";
import { LinkRow, PinPad, type PadHeader } from "./PinPad";
import { CodeStep, PausedStep, PhoneStep } from "./steps";

const CODE_TRIES = 5;
const RESEND_SECONDS = 60;

type Step = "phone" | "pad" | "code" | "paused";
type Mode = "enter" | "unlock" | "choose" | "confirm";
// signin: PIN then (on a new phone) an email code. setup and reset: an email code, then a new PIN.
type Flow = "signin" | "setup" | "reset";

type Props = {
  // Who this phone is trusted for; the flow opens on their unlock pad.
  trusted: StoredPerson | null;
  brand?: BrandInfo;
  onSignedIn: (person: StoredPerson, offline: boolean) => void;
  // After "Not you?" or "Sign in as someone else" has made the phone forget the person.
  onForgotten?: () => void;
};

export function AuthFlow({ trusted, brand, onSignedIn, onForgotten }: Props) {
  const network = useNetworkState();
  const online =
    network.isConnected !== false && network.isInternetReachable !== false;

  const [person, setPerson] = useState(trusted);
  const [step, setStep] = useState<Step>(trusted ? "pad" : "phone");
  const [mode, setMode] = useState<Mode>(trusted ? "unlock" : "enter");
  const [flow, setFlow] = useState<Flow>("signin");
  const [phone, setPhone] = useState(trusted?.phoneNumber ?? "");
  const [phoneInput, setPhoneInput] = useState("");
  const [phoneMessage, setPhoneMessage] = useState({ field: "", banner: "" });

  const [pin, setPin] = useState("");
  const [pinLength, setPinLength] = useState(trusted?.pinLength ?? 4);
  const [longPin, setLongPin] = useState(false);
  const [chosen, setChosen] = useState("");
  const [padError, setPadError] = useState("");
  const [shake, setShake] = useState(0);

  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState("");
  const [codeDead, setCodeDead] = useState(false);
  const [codeLead, setCodeLead] = useState("");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [developmentCode, setDevelopmentCode] = useState("");
  const [resendIn, setResendIn] = useState(0);

  const [pausedUntil, setPausedUntil] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [busy, setBusy] = useState(false);

  // Never rendered: the PIN behind a new-phone challenge (so "Send a new code" can repeat that sign-in and
  // the phone can keep its offline check afterwards), the code a new PIN will be saved with, and wrong-PIN counts.
  const challengePin = useRef("");
  const verifiedCode = useRef("");
  const codeTries = useRef(0);
  const pinTries = useRef<Record<string, number>>({});

  const trustedHere = Boolean(person && person.phoneNumber === phone);
  // Wrong PINs before sign-in pauses, and for how long: the organization's policy as this phone last loaded it
  // (5 and 15 minutes until it has). The phone counts so it can say how many tries are left and pause offline unlock.
  const policy = trustedHere && person ? person : DEFAULT_PIN_POLICY;
  const triesAllowed = policy.lockoutThreshold;
  const pauseSeconds = policy.lockoutMinutes * 60;

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = setTimeout(() => setResendIn((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendIn]);

  useEffect(() => {
    if (!pausedUntil) return;
    const tick = () => {
      const left = Math.max(0, Math.ceil((pausedUntil - Date.now()) / 1000));
      setRemaining(left);
      if (left > 0) return;
      setPausedUntil(0);
      pinTries.current[phone] = 0;
      void saveOfflineTries({ count: 0, pausedUntil: 0 });
      openPad(trustedHere ? "unlock" : "enter");
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
    // openPad only reads state that this effect's inputs already cover.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pausedUntil]);

  // A pause from wrong PINs typed offline outlives restarting the app.
  useEffect(() => {
    if (!trusted) return;
    void loadOfflineTries().then((tries) => {
      if (tries.pausedUntil > Date.now()) pause(tries.pausedUntil);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function openPad(next: Mode, error = "") {
    setMode(next);
    setPin("");
    setPadError(error);
    setStep("pad");
  }

  function pause(until: number) {
    setPausedUntil(until);
    setRemaining(Math.max(0, Math.ceil((until - Date.now()) / 1000)));
    setStep("paused");
  }

  function wrongPin() {
    setShake((value) => value + 1);
    const count = (pinTries.current[phone] ?? 0) + 1;
    pinTries.current[phone] = count;
    if (count >= triesAllowed) return pause(Date.now() + pauseSeconds * 1000);
    const left = triesAllowed - count;
    setPadError(`Wrong PIN. ${left} ${left === 1 ? "try" : "tries"} left.`);
  }

  function failure(
    error: unknown,
    offlineMessage = "No internet. Check your connection and try again.",
  ) {
    if (error instanceof OfflineError) return offlineMessage;
    if (error instanceof AuthError && error.httpStatus === 429)
      return "Too many requests. Please wait a minute.";
    return error instanceof AuthError
      ? error.message
      : "Something went wrong. Please try again.";
  }

  async function signedIn(result: AuthResponse, usedPin: string) {
    await keepSession(phone, result);
    await savePinCheck(usedPin);
    await saveOfflineTries({ count: 0, pausedUntil: 0 });
    pinTries.current[phone] = 0;
    const fallback =
      trustedHere && person
        ? person
        : {
            phoneNumber: phone,
            firstName: "",
            lastName: "",
            role: "",
            permissions: [],
            pinLength: usedPin.length,
            ...DEFAULT_PIN_POLICY,
          };
    onSignedIn(
      await fetchPerson(phone, usedPin.length).catch(() => ({
        ...fallback,
        pinLength: usedPin.length,
      })),
      false,
    );
  }

  function showCode(lead: string, result: AuthResponse) {
    setCode("");
    setCodeError("");
    setCodeDead(false);
    setCodeLead(lead);
    setMaskedEmail(result.maskedEmail || "");
    setDevelopmentCode(result.developmentCode || "");
    setResendIn(RESEND_SECONDS);
    codeTries.current = 0;
    setStep("code");
  }

  // ---------- Mobile number ----------
  function continueWithPhone(next: Flow) {
    const digits = normalisePhone(phoneInput);
    const invalid = phoneError(digits);
    if (invalid) return setPhoneMessage({ field: invalid, banner: "" });
    setPhone(digits);
    setFlow(next);
    if (next === "signin") {
      setPinLength(person?.phoneNumber === digits ? person.pinLength : 4);
      setLongPin(false);
      openPad("enter");
    } else void requestCode(next, digits);
  }

  // ---------- Email code for a first PIN or a reset ----------
  async function requestCode(next: Flow, number = phone) {
    setFlow(next);
    setBusy(true);
    try {
      const result = await authApi(
        next === "setup" ? "setup-pin/request" : "pin-reset/request",
        { phoneNumber: number },
      );
      showCode("", result);
    } catch (error) {
      const message = failure(
        error,
        "No internet. Sending a code needs network.",
      );
      if (step === "phone") setPhoneMessage({ field: "", banner: message });
      else if (step === "code") setCodeError(message);
      else setPadError(message);
    } finally {
      setBusy(false);
    }
  }

  // ---------- PIN pad ----------
  function press(digit: string) {
    if (busy || pin.length >= (longPin ? 8 : pinLength)) return;
    const next = pin + digit;
    setPin(next);
    setPadError("");
    if (longPin || next.length < pinLength) return;
    // A moment with every dot filled, so the last press registers, before the PIN is checked.
    setBusy(true);
    setTimeout(() => {
      setBusy(false);
      void complete(next);
    }, 180);
  }

  async function complete(entered: string) {
    setPin("");
    if (mode === "choose") {
      const weak = validatePin(entered);
      if (weak) {
        setShake((value) => value + 1);
        return setPadError("Too easy to guess. Choose different numbers.");
      }
      if (flow === "reset" && trustedHere && (await matchesPinCheck(entered))) {
        setShake((value) => value + 1);
        return setPadError("Pick a PIN different from your old one.");
      }
      setChosen(entered);
      return openPad("confirm");
    }
    if (mode === "confirm") {
      if (entered !== chosen) {
        setShake((value) => value + 1);
        return openPad(
          "choose",
          "The two PINs did not match. Choose your PIN again.",
        );
      }
      return savePin(entered);
    }
    return checkPin(entered);
  }

  async function checkPin(entered: string) {
    setBusy(true);
    try {
      const result = await authApi(mode === "unlock" ? "unlock" : "sign-in", {
        phoneNumber: phone,
        pin: entered,
      });
      if (result.status === "authenticated")
        return await signedIn(result, entered);
      if (result.status === "verification_required") {
        challengePin.current = entered;
        setFlow("signin");
        return showCode("New phone. ", result);
      }
    } catch (error) {
      if (error instanceof AuthError && error.response.status === "paused")
        return pause(
          Date.now() +
            (error.response.retryAfterSeconds ?? pauseSeconds) * 1000,
        );
      // The PIN this phone last signed in with, refused online: the person's number (or PIN) was changed
      // elsewhere, so another try cannot help and must not count toward a pause.
      if (
        error instanceof AuthError &&
        error.httpStatus === 401 &&
        mode === "unlock" &&
        (await matchesPinCheck(entered))
      )
        return setPadError(
          'This phone can no longer unlock with your PIN. If your mobile number changed, choose "Not you? Switch user" and sign in again.',
        );
      if (error instanceof AuthError && error.httpStatus === 401)
        return wrongPin();
      if (error instanceof OfflineError && mode === "unlock")
        return unlockOffline(entered);
      setPadError(
        failure(
          error,
          "No internet. Signing in on this phone for the first time needs network.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  // PIN unlock works without internet: the phone checks the PIN against the hash it kept at the last sign-in.
  async function unlockOffline(entered: string) {
    const match = await matchesPinCheck(entered);
    if (match === null || !person)
      return setPadError("No internet. Connect to unlock this phone.");
    // D7: after 72 hours away from the server the phone stops opening on its PIN alone. Captures waiting
    // to be sent are kept, so connecting once costs nothing but the connection.
    const until = await offlineUnlockUntil();
    if (until !== null && Date.now() > until)
      return setPadError(
        `This phone has been offline for more than ${OFFLINE_UNLOCK_HOURS} hours. Connect to the internet and unlock once to carry on. Anything waiting to be sent is kept.`,
      );
    const tries = await loadOfflineTries();
    if (match) {
      await saveOfflineTries({ count: 0, pausedUntil: 0 });
      return onSignedIn(person, true);
    }
    const count = tries.count + 1;
    setShake((value) => value + 1);
    if (count >= triesAllowed) {
      const until = Date.now() + pauseSeconds * 1000;
      await saveOfflineTries({ count: 0, pausedUntil: until });
      return pause(until);
    }
    await saveOfflineTries({ count, pausedUntil: 0 });
    const left = triesAllowed - count;
    setPadError(`Wrong PIN. ${left} ${left === 1 ? "try" : "tries"} left.`);
  }

  async function savePin(entered: string) {
    setBusy(true);
    try {
      const result = await authApi(
        flow === "setup" ? "setup-pin/complete" : "pin-reset/complete",
        { phoneNumber: phone, pin: entered, code: verifiedCode.current },
      );
      if (result.status === "authenticated") await signedIn(result, entered);
    } catch (error) {
      if (
        error instanceof AuthError &&
        error.response.status === "invalid_pin"
      ) {
        const shortest = error.response.minimumPinLength ?? 4;
        setPinLength(shortest);
        return openPad(
          "choose",
          `Your organization needs a PIN of at least ${shortest} numbers.`,
        );
      }
      if (error instanceof AuthError && error.httpStatus === 401) {
        setStep("code");
        setCodeDead(true);
        setResendIn(0);
        return setCodeError("This code no longer works. Tap Send a new code.");
      }
      setPadError(failure(error));
    } finally {
      setBusy(false);
    }
  }

  // ---------- Email code ----------
  function typeCode(value: string) {
    const digits = value.replace(/\D/g, "").slice(0, 6);
    setCode(digits);
    if (!codeDead) setCodeError("");
    if (digits.length === 6 && !codeDead) void confirmCode(digits);
  }

  async function confirmCode(entered = code) {
    if (busy) return;
    if (codeDead)
      return setCodeError("This code no longer works. Tap Send a new code.");
    if (entered.length !== 6)
      return setCodeError(
        entered ? "The code has 6 numbers." : "Enter the code from your email.",
      );
    setBusy(true);
    try {
      if (flow === "signin") {
        const result = await authApi("verify-device", {
          phoneNumber: phone,
          code: entered,
        });
        if (result.status === "authenticated")
          await signedIn(result, challengePin.current);
      } else {
        const result = await authApi(
          flow === "setup" ? "setup-pin/verify" : "pin-reset/verify",
          { phoneNumber: phone, code: entered },
        );
        if (result.status === "code_verified") {
          verifiedCode.current = entered;
          setChosen("");
          openPad("choose");
        }
      }
    } catch (error) {
      if (error instanceof AuthError && error.httpStatus === 401) {
        setCode("");
        codeTries.current += 1;
        if (codeTries.current >= CODE_TRIES) {
          setCodeDead(true);
          setResendIn(0);
          return setCodeError("Too many wrong codes. Tap Send a new code.");
        }
        const left = CODE_TRIES - codeTries.current;
        return setCodeError(
          `That code is wrong. ${left} ${left === 1 ? "try" : "tries"} left.`,
        );
      }
      setCodeError(failure(error));
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    if (flow !== "signin") return requestCode(flow);
    setBusy(true);
    try {
      const result = await authApi("sign-in", {
        phoneNumber: phone,
        pin: challengePin.current,
      });
      if (result.status === "verification_required")
        showCode("New phone. ", result);
      else if (result.status === "authenticated")
        await signedIn(result, challengePin.current);
    } catch (error) {
      setCodeError(failure(error));
    } finally {
      setBusy(false);
    }
  }

  function cancelCode() {
    setResendIn(0);
    if (trustedHere) openPad("unlock");
    else if (flow === "signin") openPad("enter");
    else setStep("phone");
  }

  // ---------- Switch user ----------
  // The phone stops being trusted for this person: their refresh tokens are revoked (best effort when
  // offline) and everything kept for them on the phone is removed.
  async function switchUser() {
    setBusy(true);
    await forgetThisPhone();
    onForgotten?.();
    setBusy(false);
    setPerson(null);
    setPhone("");
    setPhoneInput("");
    setPhoneMessage({ field: "", banner: "" });
    setPausedUntil(0);
    setFlow("signin");
    setStep("phone");
  }

  const layout = (content: ReactNode, footnote?: string) => (
    <AuthLayout brand={brand} footnote={footnote}>
      {content}
    </AuthLayout>
  );

  if (step === "phone")
    return layout(
      <PhoneStep
        value={phoneInput}
        error={phoneMessage.field}
        banner={phoneMessage.banner}
        online={online}
        busy={busy}
        onChange={(value) => {
          setPhoneInput(formatPhone(normalisePhone(value)));
          setPhoneMessage({ field: "", banner: "" });
        }}
        onContinue={() => continueWithPhone("signin")}
        onFirstTime={() => continueWithPhone("setup")}
      />,
    );

  if (step === "code")
    return layout(
      <CodeStep
        lead={codeLead}
        email={maskedEmail}
        value={code}
        error={codeError}
        busy={busy}
        dead={codeDead}
        resendIn={resendIn}
        developmentCode={developmentCode}
        onChange={typeCode}
        onConfirm={() => void confirmCode()}
        onResend={() => void resend()}
        onCancel={cancelCode}
      />,
    );

  if (step === "paused")
    return layout(
      <PausedStep
        remaining={remaining}
        busy={busy}
        onReset={() => void requestCode("reset")}
        onSwitch={() => void switchUser()}
      />,
    );

  const personal = mode === "unlock" || mode === "enter";
  const known = trustedHere && person ? person : null;
  const header: PadHeader = personal
    ? {
        kind: "person",
        initials: known ? initials(known) : "",
        title: known?.firstName
          ? `${mode === "unlock" ? "Welcome back" : "Hi"}, ${known.firstName}`
          : formatPhone(phone),
        sub: known ? maskPhone(phone) : "Enter the PIN for this number",
      }
    : {
        kind: "heading",
        title:
          mode === "confirm"
            ? "Type it again"
            : flow === "reset"
              ? "Choose a new PIN"
              : "Choose your PIN",
        sub:
          mode === "confirm"
            ? `Enter the same ${pinLength} numbers to confirm.`
            : `Pick ${pinLength} numbers only you know. Avoid ${"123456789".slice(0, pinLength)} or the same number ${pinLength === 4 ? "four" : pinLength} times.`,
      };

  const links = personal ? (
    <>
      <LinkRow>
        <LinkButton
          align="start"
          disabled={busy}
          onPress={() => void switchUser()}
        >
          {mode === "unlock" ? "Not you? Switch user" : "Not you?"}
        </LinkButton>
        <LinkButton
          align="end"
          disabled={busy}
          onPress={() => void requestCode("reset")}
        >
          Forgot PIN?
        </LinkButton>
      </LinkRow>
      {/* PINs are 4 numbers unless an organization asks for more. A phone that has not signed in
          before cannot know, so a longer PIN is typed in full and sent with Continue. */}
      {longPin ? (
        <LinkRow>
          <LinkButton
            align="start"
            disabled={busy || pin.length < 4}
            onPress={() => void complete(pin)}
          >
            Continue
          </LinkButton>
        </LinkRow>
      ) : (
        mode === "enter" &&
        !known &&
        pinLength === 4 && (
          <LinkRow>
            <LinkButton
              align="start"
              disabled={busy}
              onPress={() => setLongPin(true)}
            >
              My PIN has more than 4 numbers
            </LinkButton>
          </LinkRow>
        )
      )}
    </>
  ) : mode === "confirm" ? (
    <LinkRow>
      <LinkButton
        align="start"
        disabled={busy}
        onPress={() => openPad("choose")}
      >
        Start again
      </LinkButton>
    </LinkRow>
  ) : null;

  return layout(
    <PinPad
      header={header}
      label={
        personal
          ? "Enter your PIN"
          : mode === "confirm"
            ? "Confirm PIN"
            : "New PIN"
      }
      length={longPin ? Math.max(4, pin.length) : pinLength}
      value={pin}
      error={padError}
      busy={busy}
      shake={shake}
      onDigit={press}
      onDelete={() => !busy && setPin((value) => value.slice(0, -1))}
      links={links}
    />,
    mode === "unlock" ? "PIN unlock works without internet." : undefined,
  );
}
