import type { Dispatch } from "react";

import {
  AuthError,
  inviteProblemText,
  pinProblemText,
  validatePin,
  type AuthRequest,
  type AuthResponse,
  type CodePurpose,
} from "@xcode/shared/auth";
import { formatPhone, normalisePhone, phoneError } from "@xcode/shared/format";

import {
  OfflineError,
  authApi,
  forgetThisPhone,
  isNoInternet,
  keepSession,
  wakeServer,
} from "../lib/api";
import {
  OFFLINE_UNLOCK_HOURS,
  matchesPinCheck,
  offlineUnlockUntil,
  savePinCheck,
  type StoredPerson,
} from "../lib/storage";
import { fetchPerson } from "../session";
import {
  GONE_CODE_MESSAGE,
  wrongPinMessage,
  type Attempts,
  type Outcome,
} from "./attempts";
import {
  expectStatus,
  failureMessage,
  isBlocked,
  isPaused,
  isPinLocked,
  isRefused,
  profileFailedMessage,
  type CheckedOperation,
} from "./authErrors";
import {
  isPersonalPad,
  limitsOf,
  padLimit,
  type Action,
  type AuthState,
  type CodeScreen,
  type Flow,
  type PadScreen,
} from "./authFlowState";
import type { DelayedSubmit, OperationLock } from "./hooks";

export type AuthContext = {
  // The newest state.
  state(): AuthState;
  dispatch: Dispatch<Action>;
  lock: OperationLock;
  delayed: DelayedSubmit;
  attempts: Attempts;
  alive(): boolean;
  onSignedIn(person: StoredPerson, offline: boolean): void;
  onForgotten(): void;
};

// The phone is the person's own, so every code it confirms keeps it trusted.
const TRUST_THIS_PHONE = true;

const PURPOSE_OF: Record<Flow, CodePurpose> = {
  signin: "new_device",
  setup: "first_setup",
  reset: "pin_reset",
};

const FLOW_OF: Record<CodePurpose, Flow> = {
  new_device: "signin",
  first_setup: "setup",
  pin_reset: "reset",
};

const unexpected = () => new AuthError({ status: "unexpected_response" }, 200);

function flowOf(result: AuthResponse): Flow {
  const flow = result.purpose ? FLOW_OF[result.purpose] : undefined;
  if (!flow) throw unexpected();
  return flow;
}

async function send(
  operation: CheckedOperation,
  request: AuthRequest,
): Promise<AuthResponse> {
  return expectStatus(operation, await authApi(operation, request));
}

const codeDetails = (result: AuthResponse) => ({
  invitation: result.invitation === true,
  maskedEmail: result.maskedEmail || "",
  developmentCode: result.developmentCode || "",
});

// A code the server sent: confirming this phone after the PIN, or setting a new PIN.
function showCode(
  ctx: AuthContext,
  result: AuthResponse,
  flow: Flow,
  challengePin: string,
) {
  if (flow === "signin")
    ctx.dispatch({
      type: "codeRequested",
      flow,
      challengePin,
      lead: "New phone. ",
      ...codeDetails(result),
    });
  else
    ctx.dispatch({
      type: "codeRequested",
      flow,
      lead: "",
      ...codeDetails(result),
    });
}

// Everything after the server accepted a sign-in.
async function finishSignIn(
  ctx: AuthContext,
  result: AuthResponse,
  usedPin: string,
  consumedCode: boolean,
) {
  const { phone } = ctx.state();
  try {
    await keepSession(phone, result);
    await savePinCheck(usedPin, result.accessToken).catch(() => undefined);
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

// PIN unlock works without internet
async function unlockOffline(
  ctx: AuthContext,
  entered: string,
  failure: unknown,
) {
  const { person, phone } = ctx.state();
  const match = await matchesPinCheck(entered);
  if (match === null || !person)
    return ctx.dispatch({
      type: "padError",
      message: isNoInternet(failure)
        ? "No internet. Connect to unlock this phone."
        : "Can't reach the XCODE server right now. Try again shortly.",
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
  // The server counts wrong PINs across every device; at its limit only a PIN reset helps.
  if (isPinLocked(error) || isBlocked(error))
    return ctx.dispatch({ type: "padError", message: error.message });
  // The PIN this phone last signed in with, refused online: the person's number (or PIN) was changed
  // elsewhere, so another try cannot help.
  if (isRefused(error) && mode === "unlock" && (await matchesPinCheck(entered)))
    return ctx.dispatch({
      type: "padError",
      message:
        'This phone can no longer unlock with your PIN. If your mobile number changed, choose "Not you? Switch user" and sign in again.',
    });
  if (isRefused(error)) {
    const left = error.response.triesLeft;
    return typeof left === "number"
      ? ctx.dispatch({
          type: "padError",
          message: wrongPinMessage(left),
          shake: true,
        })
      : showOutcome(
          ctx,
          ctx.attempts.wrongOnline(ctx.state().phone, limitsOf(ctx.state())),
        );
  }
  if (
    mode === "unlock" &&
    (error instanceof OfflineError ||
      (error instanceof AuthError && error.httpStatus >= 500))
  )
    return unlockOffline(ctx, entered, error);
  ctx.dispatch({
    type: "padError",
    message: failureMessage(
      error,
      "No internet. Signing in on this phone for the first time needs network.",
    ),
  });
}

// The PIN signs in. A phone without this person's trusted-device token is confirmed with an emailed code first.
async function checkPin(
  ctx: AuthContext,
  entered: string,
  mode: "enter" | "unlock",
) {
  const { phone } = ctx.state();
  try {
    const result = await send("pin", { phoneNumber: phone, pin: entered });
    if (result.status === "authenticated")
      await finishSignIn(ctx, result, entered, false);
    else showCode(ctx, result, flowOf(result), entered);
  } catch (error) {
    await failPad(ctx, error, entered, mode);
  }
}

// Reusing the old PIN is refused by the server once the new one is confirmed.
function choosePin(ctx: AuthContext, entered: string) {
  if (validatePin(entered, ctx.state().pinLength))
    return ctx.dispatch({
      type: "padError",
      message: "Too easy to guess. Choose different numbers.",
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
    const result = await send("pin/new", {
      phoneNumber: ctx.state().phone,
      purpose: PURPOSE_OF[pad.flow],
      code: pad.code,
      pin: entered,
      trustDevice: TRUST_THIS_PHONE,
    });
    await finishSignIn(ctx, result, entered, true);
  } catch (error) {
    if (error instanceof AuthError && error.response.status === "invalid_pin") {
      const { pinProblem, minimumPinLength } = error.response;
      ctx.dispatch(
        pinProblem && pinProblem !== "length"
          ? { type: "pinRefused", message: pinProblemText(pinProblem) }
          : { type: "pinTooShort", minimum: minimumPinLength ?? 4 },
      );
    } else if (isRefused(error))
      ctx.dispatch({ type: "codeDead", message: GONE_CODE_MESSAGE });
    else ctx.dispatch({ type: "padError", message: failureMessage(error) });
  }
}

async function submitPin(ctx: AuthContext, entered: string) {
  const pad = ctx.state().screen;
  try {
    if (pad.step !== "pad") return;
    ctx.dispatch({ type: "pinSubmitted" });
    if (isPersonalPad(pad)) return await checkPin(ctx, entered, pad.mode);
    if (pad.mode === "choose") return choosePin(ctx, entered);
    if (entered === pad.chosen) return await savePin(ctx, entered, pad);
    ctx.dispatch({ type: "pinsDiffer" });
  } finally {
    ctx.lock.release();
  }
}

// The number decides what comes next: the PIN, or a code to set one (from the invitation email when there is one).
async function start(ctx: AuthContext, phoneNumber: string) {
  if (!ctx.lock.acquire()) return;
  try {
    const result = await send("start", { phoneNumber });
    if (result.status === "pin_required")
      return ctx.dispatch({ type: "padOpened", mode: "enter" });
    const flow = flowOf(result);
    if (flow === "signin") throw unexpected();
    showCode(ctx, result, flow, "");
  } catch (error) {
    if (isPinLocked(error)) {
      // The pad is where "Forgot PIN?" is.
      ctx.dispatch({ type: "padOpened", mode: "enter" });
      ctx.dispatch({ type: "padError", message: error.message });
    } else
      ctx.dispatch({
        type: "errorShown",
        message: failureMessage(
          error,
          "No internet. Signing in needs network.",
        ),
      });
  } finally {
    ctx.lock.release();
  }
}

async function forgotPin(ctx: AuthContext) {
  if (!ctx.lock.acquire()) return;
  try {
    const result = await send("pin/forgot", { phoneNumber: ctx.state().phone });
    showCode(ctx, result, "reset", "");
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
  const result = await send("code", {
    phoneNumber: ctx.state().phone,
    purpose: PURPOSE_OF[screen.flow],
    code: entered,
    trustDevice: TRUST_THIS_PHONE,
  });
  if (result.status === "code_resent")
    return ctx.dispatch({ type: "codeResent" });
  if (screen.flow === "signin") {
    if (result.status !== "authenticated") throw unexpected();
    return finishSignIn(ctx, result, screen.challengePin, true);
  }
  if (result.status !== "code_verified") throw unexpected();
  ctx.dispatch({ type: "codeVerified", code: entered });
}

async function confirmCode(ctx: AuthContext, typed?: string) {
  const screen = ctx.state().screen;
  if (screen.step !== "code" || ctx.lock.held()) return;
  const entered = typed ?? screen.value;
  const problem = screen.dead
    ? GONE_CODE_MESSAGE
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
        ? { type: "codeWrong", triesLeft: error.response.triesLeft ?? null }
        : { type: "errorShown", message: failureMessage(error) },
    );
  } finally {
    ctx.lock.release();
  }
}

// A fresh code for the same purpose. The answer never names the address, so the screen keeps the one it had.
async function resend(ctx: AuthContext) {
  const screen = ctx.state().screen;
  if (screen.step !== "code" || !ctx.lock.acquire()) return;
  try {
    const result = await send("code/resend", {
      phoneNumber: ctx.state().phone,
      purpose: PURPOSE_OF[screen.flow],
    });
    showCode(
      ctx,
      {
        ...result,
        invitation: false,
        maskedEmail: result.maskedEmail || screen.maskedEmail,
      },
      screen.flow,
      screen.flow === "signin" ? screen.challengePin : "",
    );
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

// The invitation link and the number the person confirmed. A phone trusted for someone else stops being theirs only
// once the invitation matched.
async function redeemInvite(ctx: AuthContext) {
  const { screen, phoneInput, person } = ctx.state();
  if (screen.step !== "invite") return;
  const digits = normalisePhone(phoneInput);
  const invalid = phoneError(digits);
  if (invalid) return ctx.dispatch({ type: "phoneRejected", message: invalid });
  if (!ctx.lock.acquire()) return;
  try {
    const result = await send("invite/redeem", {
      token: screen.token,
      phoneNumber: digits,
    });
    if (result.purpose !== "first_setup" || !result.code) throw unexpected();
    if (person) await forgetThisPhone();
    if (!ctx.alive()) return;
    ctx.dispatch({ type: "phoneAccepted", phone: digits });
    ctx.dispatch({ type: "inviteRedeemed", code: result.code });
  } catch (error) {
    ctx.dispatch({
      type: "errorShown",
      message: isRefused(error)
        ? inviteProblemText(error.response.inviteProblem)
        : failureMessage(
            error,
            "No internet. Setting up your access needs network.",
          ),
    });
  } finally {
    ctx.lock.release();
  }
}

function continueWithPhone(ctx: AuthContext) {
  const digits = normalisePhone(ctx.state().phoneInput);
  const invalid = phoneError(digits);
  if (invalid) return ctx.dispatch({ type: "phoneRejected", message: invalid });
  ctx.dispatch({ type: "phoneAccepted", phone: digits });
  void start(ctx, digits);
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
  // A server gone idle wakes while the rest of the PIN is typed.
  if (entered.length === 1) wakeServer();
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
    continueWithPhone: () => continueWithPhone(ctx),
    // False while another step is running: the caller keeps the token and tries again after it.
    openInvite: (token: string): boolean => {
      if (ctx.lock.held()) return false;
      ctx.dispatch({ type: "inviteOpened", token });
      return true;
    },
    redeemInvite: () => void redeemInvite(ctx),
    cancelInvite: () => ctx.dispatch({ type: "inviteCancelled" }),
    requestReset: () => void forgotPin(ctx),
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
