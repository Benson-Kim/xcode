export const PIN_HELP =
  "Use 4-8 digits, not all the same or an ascending/descending sequence.";

export function validatePin(pin: string): string | null {
  if (pin.length < 4 || pin.length > 8 || /[^0-9]/.test(pin)) return PIN_HELP;
  if ([...pin].every((digit) => digit === pin[0])) return PIN_HELP;
  const steps = [...pin]
    .slice(1)
    .map((digit, i) => Number(digit) - Number(pin[i]));
  if (steps.every((step) => step === 1) || steps.every((step) => step === -1))
    return PIN_HELP;
  return null;
}

export type AuthStatus =
  | "authenticated"
  | "verification_required"
  | "check_email"
  | "code_verified"
  | "paused"
  | "authentication_failed"
  | "invalid_pin"
  | "invalid_request"
  | "signed_out"
  | "device_revoked";

export interface AuthRequest {
  email?: string;
  phoneNumber?: string;
  pin?: string;
  deviceId?: string;
  code?: string;
  refreshToken?: string;
}

export interface AuthResponse {
  status: AuthStatus;
  accessToken?: string | null;
  refreshToken?: string | null;
  retryAfterSeconds?: number | null;
  developmentCode?: string | null;
  maskedEmail?: string | null;
}

export interface SessionTokens {
  accessToken: string;
  refreshToken: string;
}

export type AuthOperation =
  | "sign-in"
  | "verify-device"
  | "setup-pin/request"
  | "setup-pin/complete"
  | "pin-reset/request"
  | "pin-reset/verify"
  | "pin-reset/complete"
  | "unlock"
  | "refresh"
  | "sign-out";

export class AuthError extends Error {
  constructor(
    public readonly response: AuthResponse,
    public readonly httpStatus: number,
  ) {
    super(
      response.status === "paused"
        ? "Sign-in is paused. Try again when the timer ends, or reset your PIN."
        : response.status === "invalid_pin"
          ? PIN_HELP
          : httpStatus === 429
            ? "Too many requests. Please wait a minute."
            : "Authentication could not be completed. Check your details and try again.",
    );
  }
}

export function createAuthClient(
  baseUrl: string,
  fetcher: typeof fetch = fetch,
) {
  return async (
    operation: AuthOperation | `devices/${string}/revoke`,
    request: AuthRequest,
    accessToken?: string,
  ): Promise<AuthResponse> => {
    const response = await fetcher(`${baseUrl}/${operation}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify(request),
    });
    const body = (await response
      .json()
      .catch(() => ({ status: "authentication_failed" }))) as AuthResponse;
    if (!response.ok) throw new AuthError(body, response.status);
    return body;
  };
}

export function pauseSeconds(until: number, now = Date.now()): number {
  return Math.max(0, Math.ceil((until - now) / 1000));
}
