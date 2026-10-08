import { pauseSeconds } from "@xcode/shared/auth";
import { formatPhone, initials, maskPhone } from "@xcode/shared/format";

import { DEFAULT_PIN_POLICY, type StoredPerson } from "../lib/storage";
import { codeOutcome, type TryLimits } from "./attempts";
import type { PadHeader } from "./PinPad";

export const RESEND_SECONDS = 60;
export const LONG_PIN_DIGITS = 8;

// signin: PIN then (on a new phone) an email code. setup and reset: an email code, then a new PIN.
export type Flow = "signin" | "setup" | "reset";
export type NewPinFlow = "setup" | "reset";

type CodeView = {
  value: string;
  error: string;
  dead: boolean;
  lead: string;
  maskedEmail: string;
  developmentCode: string;
  resendIn: number;
  tries: number;
};

// The PIN, the email code and the chosen PIN exist only on the screens that need them, so a transition that
// builds another screen drops them.
export type Screen =
  | { step: "phone"; fieldError: string; banner: string }
  | {
      step: "pad";
      mode: "enter" | "unlock";
      pin: string;
      error: string;
      longPin: boolean;
    }
  | {
      step: "pad";
      mode: "choose";
      flow: NewPinFlow;
      code: string;
      pin: string;
      error: string;
    }
  | {
      step: "pad";
      mode: "confirm";
      flow: NewPinFlow;
      code: string;
      chosen: string;
      pin: string;
      error: string;
    }
  | ({ step: "code"; flow: "signin"; challengePin: string } & CodeView)
  | ({ step: "code"; flow: NewPinFlow } & CodeView)
  | { step: "paused"; until: number; remaining: number; error: string };

export type PadScreen = Extract<Screen, { step: "pad" }>;
export type CodeScreen = Extract<Screen, { step: "code" }>;

export type AuthState = {
  // Who this phone is trusted for.
  person: StoredPerson | null;
  // The digits of the number in progress, and what the number field shows.
  phone: string;
  phoneInput: string;
  pinLength: number;
  // Bumped on every wrong entry so the dots shake.
  shake: number;
  screen: Screen;
};

type CodeRequest = {
  lead: string;
  maskedEmail: string;
  developmentCode: string;
};

export type Action =
  | { type: "phoneEdited"; input: string }
  | { type: "phoneRejected"; message: string }
  | { type: "phoneAccepted"; phone: string }
  | { type: "padOpened"; mode: "enter" | "unlock" }
  | { type: "digit"; digit: string }
  | { type: "backspace" }
  | { type: "longPinChosen" }
  | { type: "pinSubmitted" }
  | { type: "padError"; message: string; shake?: boolean }
  | { type: "errorShown"; message: string }
  | { type: "pinChosen"; pin: string }
  | { type: "pinsDiffer" }
  | { type: "startAgain" }
  | { type: "pinTooShort"; minimum: number }
  | ({ type: "codeRequested" } & CodeRequest &
      ({ flow: "signin"; challengePin: string } | { flow: NewPinFlow }))
  | { type: "codeEdited"; value: string }
  | { type: "codeWrong" }
  | { type: "codeDead"; message: string }
  | { type: "resendTick" }
  | { type: "codeVerified"; code: string }
  | { type: "codeCancelled" }
  | { type: "paused"; until: number; now: number }
  | { type: "pauseTick"; now: number }
  | { type: "pauseEnded" }
  | { type: "profileFailed"; pinLength: number; message: string }
  | { type: "completed" }
  | { type: "userForgotten" };

export const trustedHere = (state: AuthState) =>
  state.person !== null && state.person.phoneNumber === state.phone;

export function limitsOf(state: AuthState): TryLimits {
  const policy =
    trustedHere(state) && state.person ? state.person : DEFAULT_PIN_POLICY;
  return {
    triesAllowed: policy.lockoutThreshold,
    lockoutSeconds: policy.lockoutMinutes * 60,
  };
}

export type PersonalPad = Extract<PadScreen, { mode: "enter" | "unlock" }>;

export const personalPad = (mode: "enter" | "unlock"): PersonalPad => ({
  step: "pad",
  mode,
  pin: "",
  error: "",
  longPin: false,
});

const padFor = (state: AuthState): PersonalPad =>
  personalPad(trustedHere(state) ? "unlock" : "enter");

export function initialState(trusted: StoredPerson | null): AuthState {
  return {
    person: trusted,
    phone: trusted?.phoneNumber ?? "",
    phoneInput: "",
    pinLength: trusted?.pinLength ?? 4,
    shake: 0,
    screen: trusted
      ? personalPad("unlock")
      : { step: "phone", fieldError: "", banner: "" },
  };
}

export const isPersonalPad = (screen: Screen): screen is PersonalPad =>
  screen.step === "pad" &&
  (screen.mode === "enter" || screen.mode === "unlock");

export const padLimit = (state: AuthState) =>
  isPersonalPad(state.screen) && state.screen.longPin
    ? LONG_PIN_DIGITS
    : state.pinLength;

export function padCopy(state: AuthState, screen: PadScreen) {
  const known = trustedHere(state) ? state.person : null;
  const { pinLength } = state;
  if (isPersonalPad(screen)) {
    const header: PadHeader = {
      kind: "person",
      initials: known ? initials(known.firstName, known.lastName) : "",
      title: known?.firstName
        ? `${screen.mode === "unlock" ? "Welcome back" : "Hi"}, ${known.firstName}`
        : formatPhone(state.phone),
      sub: known ? maskPhone(state.phone) : "Enter the PIN for this number",
    };
    return {
      header,
      label: "Enter your PIN",
      length: screen.longPin ? Math.max(4, screen.pin.length) : pinLength,
    };
  }
  const confirming = screen.mode === "confirm";
  const header: PadHeader = {
    kind: "heading",
    title: confirming
      ? "Type it again"
      : screen.flow === "reset"
        ? "Choose a new PIN"
        : "Choose your PIN",
    sub: confirming
      ? `Enter the same ${pinLength} numbers to confirm.`
      : `Pick ${pinLength} numbers only you know. Avoid ${"123456789".slice(0, pinLength)} or the same number ${pinLength === 4 ? "four" : pinLength} times.`,
  };
  return {
    header,
    label: confirming ? "Confirm PIN" : "New PIN",
    length: pinLength,
  };
}

const withScreen = (state: AuthState, screen: Screen): AuthState => ({
  ...state,
  screen,
});

const freshCode = (request: CodeRequest): CodeView => ({
  value: "",
  error: "",
  dead: false,
  lead: request.lead,
  maskedEmail: request.maskedEmail,
  developmentCode: request.developmentCode,
  resendIn: RESEND_SECONDS,
  tries: 0,
});

function reducePhone(state: AuthState, action: Action): AuthState | undefined {
  switch (action.type) {
    case "phoneEdited":
      return {
        ...state,
        phoneInput: action.input,
        screen:
          state.screen.step === "phone"
            ? { step: "phone", fieldError: "", banner: "" }
            : state.screen,
      };
    case "phoneRejected":
      return withScreen(state, {
        step: "phone",
        fieldError: action.message,
        banner: "",
      });
    case "phoneAccepted":
      return {
        ...state,
        phone: action.phone,
        pinLength:
          state.person?.phoneNumber === action.phone
            ? state.person.pinLength
            : 4,
      };
    case "padOpened":
      return withScreen(state, personalPad(action.mode));
    case "errorShown":
      return showError(state, action.message);
  }
  return undefined;
}

function showError(state: AuthState, message: string): AuthState {
  const { screen } = state;
  return withScreen(
    state,
    screen.step === "phone"
      ? { ...screen, fieldError: "", banner: message }
      : { ...screen, error: message },
  );
}

function reducePad(state: AuthState, action: Action): AuthState | undefined {
  const { screen } = state;
  if (screen.step !== "pad") return undefined;
  switch (action.type) {
    case "digit":
      return screen.pin.length >= padLimit(state)
        ? state
        : withScreen(state, {
            ...screen,
            pin: screen.pin + action.digit,
            error: "",
          });
    case "backspace":
      return withScreen(state, { ...screen, pin: screen.pin.slice(0, -1) });
    case "longPinChosen":
      return isPersonalPad(screen)
        ? withScreen(state, { ...screen, longPin: true })
        : state;
    case "pinSubmitted":
      return withScreen(state, { ...screen, pin: "" });
    case "padError":
      return {
        ...state,
        shake: state.shake + (action.shake ? 1 : 0),
        screen: { ...screen, pin: "", error: action.message },
      };
  }
  return reducePinChoice(state, screen, action);
}

function reducePinChoice(
  state: AuthState,
  screen: PadScreen,
  action: Action,
): AuthState | undefined {
  if (isPersonalPad(screen)) return undefined;
  const { flow, code } = screen;
  const choose = (error: string, pinLength = state.pinLength): AuthState => ({
    ...state,
    pinLength,
    screen: { step: "pad", mode: "choose", flow, code, pin: "", error },
  });
  switch (action.type) {
    case "pinChosen":
      return screen.mode === "choose"
        ? withScreen(state, {
            step: "pad",
            mode: "confirm",
            flow,
            code,
            chosen: action.pin,
            pin: "",
            error: "",
          })
        : state;
    case "pinsDiffer":
      return {
        ...choose("The two PINs did not match. Choose your PIN again."),
        shake: state.shake + 1,
      };
    case "startAgain":
      return choose("");
    case "pinTooShort":
      return choose(
        `Your organization needs a PIN of at least ${action.minimum} numbers.`,
        action.minimum,
      );
  }
  return undefined;
}

function reduceCode(state: AuthState, action: Action): AuthState | undefined {
  if (action.type === "codeRequested") return requestCode(state, action);
  const { screen } = state;
  if (action.type === "codeDead") return killCode(state, action.message);
  if (screen.step !== "code") return undefined;
  switch (action.type) {
    case "codeEdited":
      return withScreen(state, {
        ...screen,
        value: action.value,
        error: screen.dead ? screen.error : "",
      });
    case "codeWrong": {
      const wrong = screen.tries + 1;
      const { dead, message } = codeOutcome(wrong);
      return withScreen(state, {
        ...screen,
        value: "",
        tries: wrong,
        error: message,
        dead,
        resendIn: dead ? 0 : screen.resendIn,
      });
    }
    case "resendTick":
      return screen.resendIn > 0
        ? withScreen(state, { ...screen, resendIn: screen.resendIn - 1 })
        : state;
    case "codeVerified":
      return screen.flow === "signin"
        ? state
        : withScreen(state, {
            step: "pad",
            mode: "choose",
            flow: screen.flow,
            code: action.code,
            pin: "",
            error: "",
          });
    case "codeCancelled":
      return withScreen(
        state,
        trustedHere(state)
          ? personalPad("unlock")
          : screen.flow === "signin"
            ? personalPad("enter")
            : { step: "phone", fieldError: "", banner: "" },
      );
  }
  return undefined;
}

function requestCode(
  state: AuthState,
  action: Extract<Action, { type: "codeRequested" }>,
): AuthState {
  const view = freshCode(action);
  return withScreen(
    state,
    action.flow === "signin"
      ? {
          step: "code",
          flow: "signin",
          challengePin: action.challengePin,
          ...view,
        }
      : { step: "code", flow: action.flow, ...view },
  );
}

// A new-PIN screen whose email code was refused: the code can only be replaced.
function killCode(state: AuthState, message: string): AuthState {
  const { screen } = state;
  const flow =
    screen.step === "pad" && !isPersonalPad(screen)
      ? screen.flow
      : screen.step === "code" && screen.flow !== "signin"
        ? screen.flow
        : null;
  if (!flow) return state;
  const view = {
    ...freshCode({ lead: "", maskedEmail: "", developmentCode: "" }),
    error: message,
    dead: true,
    resendIn: 0,
  };
  return withScreen(state, { step: "code", flow, ...view });
}

function reducePause(state: AuthState, action: Action): AuthState | undefined {
  const { screen } = state;
  switch (action.type) {
    case "paused":
      return withScreen(state, {
        step: "paused",
        until: action.until,
        remaining: pauseSeconds(action.until, action.now),
        error: "",
      });
    case "pauseTick":
      return screen.step === "paused"
        ? withScreen(state, {
            ...screen,
            remaining: pauseSeconds(screen.until, action.now),
          })
        : state;
    case "pauseEnded":
      return screen.step === "paused"
        ? withScreen(state, padFor(state))
        : state;
  }
  return undefined;
}

function reduceSession(
  state: AuthState,
  action: Action,
): AuthState | undefined {
  switch (action.type) {
    case "profileFailed":
      return {
        ...state,
        pinLength: action.pinLength,
        screen: { ...padFor(state), error: action.message },
      };
    case "completed":
      return withScreen(state, padFor(state));
    case "userForgotten":
      return {
        ...state,
        person: null,
        phone: "",
        phoneInput: "",
        pinLength: 4,
        screen: { step: "phone", fieldError: "", banner: "" },
      };
  }
  return undefined;
}

export function reduce(state: AuthState, action: Action): AuthState {
  return (
    reducePhone(state, action) ??
    reducePad(state, action) ??
    reduceCode(state, action) ??
    reducePause(state, action) ??
    reduceSession(state, action) ??
    state
  );
}
