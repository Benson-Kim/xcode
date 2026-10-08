import type { Dispatch } from "react";

import {
  AuthError,
  validatePin,
  type AuthRequest,
  type AuthResponse,
} from "@xcode/shared/auth";
import { formatPhone, normalisePhone, phoneError } from "@xcode/shared/format";

import {
  OfflineError,
  authApi,
  forgetThisPhone,
  keepSession,
} from "../lib/api";
import {
  OFFLINE_UNLOCK_HOURS,
  matchesPinCheck,
  offlineUnlockUntil,
  savePinCheck,
  type StoredPerson,
} from "../lib/storage";
import { fetchPerson } from "../session";
import type { Attempts, Outcome } from "./attempts";
import {
  expectStatus,
  failureMessage,
  isPaused,
  isRefused,
  profileFailedMessage,
  type CheckedOperation,
} from "./authErrors";
import {
  isPersonalPad,
  limitsOf,
  padLimit,
  trustedHere,
  type Action,
  type AuthState,
  type CodeScreen,
  type Flow,
  type NewPinFlow,
  type PadScreen,
} from "./authFlowState";
import type { DelayedSubmit, OperationLock } from "./hooks";

export type AuthContext = {
  // The newest state. Handlers read it after every await instead of what they closed over.
  state(): AuthState;
  dispatch: Dispatch<Action>;
  lock: OperationLock;
  delayed: DelayedSubmit;
  attempts: Attempts;
  alive(): boolean;
  onSignedIn(person: StoredPerson, offline: boolean): void;
  onForgotten(): void;
};

const DEAD_CODE = "This code no longer works. Tap Send a new code.";

async function send(
  operation: CheckedOperation,
  request: AuthRequest,
): Promise<AuthResponse> {
  return expectStatus(operation, await authApi(operation, request));
}

const codeDetails = (result: AuthResponse) => ({
  maskedEmail: result.maskedEmail || "",
  developmentCode: result.developmentCode || "",
});

// Everything after the server accepted a sign-in. A failure here never replays what the server consumed:
// the person goes back to the PIN pad, where the phone is trusted now.
async function finishSignIn(
  ctx: AuthContext,
  result: AuthResponse,
  usedPin: string,
  consumedCode: boolean,
) {
  const { phone } = ctx.state();
  try {
    await keepSession(phone, result);
    await savePinCheck(usedPin);
    await ctx.attempts.clear(phone);
    const person = await fetchPerson(phone, usedPin.length);
    if (!ctx.alive()) return;
    ctx.dispatch({ type: "completed" });
    ctx.onSignedIn(person, false);
  } catch {
    if (!ctx.alive()) return;
    ctx.dispatch({
      type: "profileFailed",
      pinLength: usedPin.length,
      message: profileFailedMessage(consumedCode),
    });
  }
}

function showOutcome(ctx: AuthContext, outcome: Outcome) {
  if (outcome.kind === "paused")
    ctx.dispatch({ type: "paused", until: outcome.until, now: Date.now() });
  else
    ctx.dispatch({ type: "padError", message: outcome.message, shake: true });
}

function pauseFromServer(ctx: AuthContext, error: AuthError) {
  const seconds =
    error.response.retryAfterSeconds ?? limitsOf(ctx.state()).lockoutSeconds;
  ctx.dispatch({
    type: "paused",
    until: Date.now() + seconds * 1000,
    now: Date.now(),
  });
}

// PIN unlock works without internet: the phone checks the PIN against the hash it kept at the last sign-in.
async function unlockOffline(ctx: AuthContext, entered: string) {
  const { person, phone } = ctx.state();
  const match = await matchesPinCheck(entered);
  if (match === null || !person)
    return ctx.dispatch({
      type: "padError",
      message: "No internet. Connect to unlock this phone.",
    });

  const until = await offlineUnlockUntil();
  if (until !== null && Date.now() > until)
    return ctx.dispatch({
      type: "padError",
      message: `This phone has been offline for more than ${OFFLINE_UNLOCK_HOURS} hours. Connect to the internet and unlock once to carry on. Anything waiting to be sent is kept.`,
    });

  if (match) {
    await ctx.attempts.clear(phone);
    if (!ctx.alive()) return;
    ctx.dispatch({ type: "completed" });
    return ctx.onSignedIn(person, true);
  }
  showOutcome(ctx, await ctx.attempts.wrongOffline(limitsOf(ctx.state())));
}

async function failPad(
  ctx: AuthContext,
  error: unknown,
  entered: string,
  mode: "enter" | "unlock",
) {
  if (isPaused(error)) return pauseFromServer(ctx, error);
  // The PIN this phone last signed in with, refused online: the person's number (or PIN) was changed
  // elsewhere, so another try cannot help and must not count toward a pause.
  if (isRefused(error) && mode === "unlock" && (await matchesPinCheck(entered)))
    return ctx.dispatch({
      type: "padError",
      message:
        'This phone can no longer unlock with your PIN. If your mobile number changed, choose "Not you? Switch user" and sign in again.',
    });
  if (isRefused(error))
    return showOutcome(
      ctx,
      ctx.attempts.wrongOnline(ctx.state().phone, limitsOf(ctx.state())),
    );
  if (
    mode === "unlock" &&
    (error instanceof OfflineError ||
      (error instanceof AuthError && error.httpStatus >= 500))
  )
    return unlockOffline(ctx, entered);
  ctx.dispatch({
    type: "padError",
    message: failureMessage(
      error,
      "No internet. Signing in on this phone for the first time needs network.",
    ),
  });
}

async function checkPin(
  ctx: AuthContext,
  entered: string,
  mode: "enter" | "unlock",
) {
  const { phone } = ctx.state();
  try {
    const result = await send(mode === "unlock" ? "unlock" : "sign-in", {
      phoneNumber: phone,
      pin: entered,
    });
    if (result.status === "verification_required")
      ctx.dispatch({
        type: "codeRequested",
        flow: "signin",
        challengePin: entered,
        lead: "New phone. ",
        ...codeDetails(result),
      });
    else await finishSignIn(ctx, result, entered, false);
  } catch (error) {
    await failPad(ctx, error, entered, mode);
  }
}

async function choosePin(ctx: AuthContext, entered: string, flow: NewPinFlow) {
  const state = ctx.state();
  if (validatePin(entered, state.pinLength))
    return ctx.dispatch({
      type: "padError",
      message: "Too easy to guess. Choose different numbers.",
      shake: true,
    });
  if (
    flow === "reset" &&
    trustedHere(state) &&
    (await matchesPinCheck(entered))
  )
    return ctx.dispatch({
      type: "padError",
      message: "Pick a PIN different from your old one.",
      shake: true,
    });
  ctx.dispatch({ type: "pinChosen", pin: entered });
}

async function savePin(
  ctx: AuthContext,
  entered: string,
  pad: Extract<PadScreen, { mode: "confirm" }>,
) {
  try {
    const result = await send(
      pad.flow === "setup" ? "setup-pin/complete" : "pin-reset/complete",
      { phoneNumber: ctx.state().phone, pin: entered, code: pad.code },
    );
    await finishSignIn(ctx, result, entered, true);
  } catch (error) {
    if (error instanceof AuthError && error.response.status === "invalid_pin")
      ctx.dispatch({
        type: "pinTooShort",
        minimum: error.response.minimumPinLength ?? 4,
      });
    else if (isRefused(error))
      ctx.dispatch({ type: "codeDead", message: DEAD_CODE });
    else ctx.dispatch({ type: "padError", message: failureMessage(error) });
  }
}

async function submitPin(ctx: AuthContext, entered: string) {
  const pad = ctx.state().screen;
  try {
    if (pad.step !== "pad") return;
    ctx.dispatch({ type: "pinSubmitted" });
    if (isPersonalPad(pad)) return await checkPin(ctx, entered, pad.mode);
    if (pad.mode === "choose") return await choosePin(ctx, entered, pad.flow);
    if (entered === pad.chosen) return await savePin(ctx, entered, pad);
    ctx.dispatch({ type: "pinsDiffer" });
  } finally {
    ctx.lock.release();
  }
}

async function requestCode(
  ctx: AuthContext,
  flow: NewPinFlow,
  number?: string,
) {
  if (!ctx.lock.acquire()) return;
  try {
    const result = await send(
      flow === "setup" ? "setup-pin/request" : "pin-reset/request",
      { phoneNumber: number ?? ctx.state().phone },
    );
    ctx.dispatch({
      type: "codeRequested",
      flow,
      lead: "",
      ...codeDetails(result),
    });
  } catch (error) {
    ctx.dispatch({
      type: "errorShown",
      message: failureMessage(
        error,
        "No internet. Sending a code needs network.",
      ),
    });
  } finally {
    ctx.lock.release();
  }
}

async function verifyCode(
  ctx: AuthContext,
  screen: CodeScreen,
  entered: string,
) {
  const phoneNumber = ctx.state().phone;
  if (screen.flow === "signin") {
    const result = await send("verify-device", { phoneNumber, code: entered });
    return finishSignIn(ctx, result, screen.challengePin, true);
  }
  await send(
    screen.flow === "setup" ? "setup-pin/verify" : "pin-reset/verify",
    { phoneNumber, code: entered },
  );
  ctx.dispatch({ type: "codeVerified", code: entered });
}

async function confirmCode(ctx: AuthContext, typed?: string) {
  const screen = ctx.state().screen;
  if (screen.step !== "code" || ctx.lock.held()) return;
  const entered = typed ?? screen.value;
  const problem = screen.dead
    ? DEAD_CODE
    : entered.length === 6
      ? ""
      : entered
        ? "The code has 6 numbers."
        : "Enter the code from your email.";
  if (problem) return ctx.dispatch({ type: "errorShown", message: problem });
  if (!ctx.lock.acquire()) return;
  try {
    await verifyCode(ctx, screen, entered);
  } catch (error) {
    ctx.dispatch(
      isRefused(error)
        ? { type: "codeWrong" }
        : { type: "errorShown", message: failureMessage(error) },
    );
  } finally {
    ctx.lock.release();
  }
}

async function resend(ctx: AuthContext) {
  const screen = ctx.state().screen;
  if (screen.step !== "code") return;
  if (screen.flow !== "signin") return requestCode(ctx, screen.flow);
  if (!ctx.lock.acquire()) return;
  try {
    const result = await send("sign-in", {
      phoneNumber: ctx.state().phone,
      pin: screen.challengePin,
    });
    if (result.status === "verification_required")
      ctx.dispatch({
        type: "codeRequested",
        flow: "signin",
        challengePin: screen.challengePin,
        lead: "New phone. ",
        ...codeDetails(result),
      });
    else await finishSignIn(ctx, result, screen.challengePin, false);
  } catch (error) {
    if (isPaused(error)) pauseFromServer(ctx, error);
    else ctx.dispatch({ type: "errorShown", message: failureMessage(error) });
  } finally {
    ctx.lock.release();
  }
}

// The phone stops being trusted for this person: their refresh tokens are revoked (best effort when
// offline) and everything kept for them on the phone is removed.
async function switchUser(ctx: AuthContext) {
  if (!ctx.lock.acquire()) return;
  try {
    await forgetThisPhone();
    if (!ctx.alive()) return;
    ctx.dispatch({ type: "userForgotten" });
    ctx.onForgotten();
  } catch (error) {
    ctx.dispatch({ type: "errorShown", message: failureMessage(error) });
  } finally {
    ctx.lock.release();
  }
}

function continueWithPhone(ctx: AuthContext, flow: Flow) {
  const digits = normalisePhone(ctx.state().phoneInput);
  const invalid = phoneError(digits);
  if (invalid) return ctx.dispatch({ type: "phoneRejected", message: invalid });
  ctx.dispatch({ type: "phoneAccepted", phone: digits });
  if (flow === "signin") ctx.dispatch({ type: "padOpened", mode: "enter" });
  else void requestCode(ctx, flow, digits);
}

function press(ctx: AuthContext, digit: string) {
  const state = ctx.state();
  const pad = state.screen;
  if (
    pad.step !== "pad" ||
    ctx.lock.held() ||
    pad.pin.length >= padLimit(state)
  )
    return;
  ctx.dispatch({ type: "digit", digit });
  const entered = pad.pin + digit;
  if (isPersonalPad(pad) && pad.longPin) return;
  if (entered.length < state.pinLength || !ctx.lock.acquire()) return;
  ctx.delayed.schedule(() => void submitPin(ctx, entered));
}

function submitLongPin(ctx: AuthContext) {
  const pad = ctx.state().screen;
  if (pad.step !== "pad" || !ctx.lock.acquire()) return;
  void submitPin(ctx, pad.pin);
}

function pauseEnded(ctx: AuthContext) {
  void ctx.attempts.clear(ctx.state().phone);
  if (ctx.delayed.cancel()) ctx.lock.release();
  ctx.dispatch({ type: "pauseEnded" });
}

export function createAuthActions(ctx: AuthContext) {
  return {
    editPhone: (input: string) =>
      ctx.dispatch({
        type: "phoneEdited",
        input: formatPhone(normalisePhone(input)),
      }),
    continueWithPhone: (flow: Flow) => continueWithPhone(ctx, flow),
    requestReset: () => void requestCode(ctx, "reset"),
    press: (digit: string) => press(ctx, digit),
    backspace: () => {
      if (!ctx.lock.held()) ctx.dispatch({ type: "backspace" });
    },
    chooseLongPin: () => ctx.dispatch({ type: "longPinChosen" }),
    submitLongPin: () => submitLongPin(ctx),
    startAgain: () => ctx.dispatch({ type: "startAgain" }),
    typeCode: (value: string) => {
      const digits = value.replace(/\D/g, "").slice(0, 6);
      ctx.dispatch({ type: "codeEdited", value: digits });
      const screen = ctx.state().screen;
      if (digits.length === 6 && screen.step === "code" && !screen.dead)
        void confirmCode(ctx, digits);
    },
    confirmCode: () => void confirmCode(ctx),
    resend: () => void resend(ctx),
    cancelCode: () => ctx.dispatch({ type: "codeCancelled" }),
    switchUser: () => void switchUser(ctx),
    pauseEnded: () => pauseEnded(ctx),
  };
}

export type AuthActions = ReturnType<typeof createAuthActions>;
