import {
  AuthError,
  type AuthResponse,
  type AuthStatus,
} from "@xcode/shared/auth";

import { OfflineError, ServerError, ServerUnreachableError } from "../lib/api";

export const OFFLINE_MESSAGE =
  "No internet. Check your connection and try again.";

// The text for a failed call. An AuthError already says what to do for a rate limit or an unavailable service.
export function failureMessage(
  error: unknown,
  offlineMessage = OFFLINE_MESSAGE,
): string {
  if (error instanceof ServerUnreachableError || error instanceof ServerError)
    return error.message;
  if (error instanceof OfflineError) return offlineMessage;
  return error instanceof AuthError
    ? error.message
    : "Something went wrong. Please try again.";
}

export const profileFailedMessage = (consumedCode: boolean) =>
  consumedCode
    ? "Signed in, but your profile could not be loaded. Enter your PIN to try again."
    : "Signed in, but your profile could not be loaded. Check your connection and try again.";

// What each call may answer with a 2xx. Anything else is a fault in the service, never a result to act on.
const EXPECTED = {
  start: ["pin_required", "verification_required"],
  pin: ["authenticated", "verification_required"],
  code: ["authenticated", "code_verified", "code_resent"],
  "code/resend": ["verification_required"],
  "pin/forgot": ["verification_required"],
  "pin/new": ["authenticated"],
  "invite/redeem": ["verification_required"],
} as const satisfies Record<string, readonly AuthStatus[]>;

export type CheckedOperation = keyof typeof EXPECTED;

export function expectStatus(
  operation: CheckedOperation,
  result: AuthResponse,
): AuthResponse {
  if (!(EXPECTED[operation] as readonly AuthStatus[]).includes(result.status))
    throw new AuthError({ status: "unexpected_response" }, 200);
  return result;
}

export const isPaused = (error: unknown): error is AuthError =>
  error instanceof AuthError && error.response.status === "paused";

export const isRefused = (error: unknown): error is AuthError =>
  error instanceof AuthError && error.httpStatus === 401;

// Too many wrong PINs on every device: only a PIN reset signs the person in again.
export const isPinLocked = (error: unknown): error is AuthError =>
  error instanceof AuthError && error.response.status === "pin_locked";

export const isBlocked = (error: unknown): error is AuthError =>
  error instanceof AuthError && error.response.status === "blocked";
