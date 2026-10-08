import {
  AuthError,
  type AuthResponse,
  type AuthStatus,
} from "@xcode/shared/auth";

import { OfflineError } from "../lib/api";

export const OFFLINE_MESSAGE =
  "No internet. Check your connection and try again.";

// The text for a failed call. An AuthError already says what to do for a rate limit or an unavailable service.
export function failureMessage(
  error: unknown,
  offlineMessage = OFFLINE_MESSAGE,
): string {
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
  "sign-in": ["authenticated", "verification_required"],
  unlock: ["authenticated", "verification_required"],
  "verify-device": ["authenticated"],
  "setup-pin/request": ["check_email"],
  "setup-pin/verify": ["code_verified"],
  "setup-pin/complete": ["authenticated"],
  "pin-reset/request": ["check_email"],
  "pin-reset/verify": ["code_verified"],
  "pin-reset/complete": ["authenticated"],
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
