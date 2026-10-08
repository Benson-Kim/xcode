export function pinHelp(minimumLength = 4): string {
  return `Use ${minimumLength}-8 digits, not all the same or an ascending/descending sequence.`;
}

export const PIN_HELP = pinHelp();

export function validatePin(pin: string, minimumLength = 4): string | null {
  const help = pinHelp(minimumLength);
  if (pin.length < minimumLength || pin.length > 8 || /[^0-9]/.test(pin))
    return help;
  if ([...pin].every((digit) => digit === pin[0])) return help;
  const steps = [...pin]
    .slice(1)
    .map((digit, i) => Number(digit) - Number(pin[i]));
  if (steps.every((step) => step === 1) || steps.every((step) => step === -1))
    return help;
  return null;
}

// Every status the API sends. 503 service_unavailable: it could not finish right now, for example a
// new-device email could not be sent.
export const AUTH_STATUSES = [
  "authenticated",
  "verification_required",
  "check_email",
  "code_verified",
  "paused",
  "authentication_failed",
  "invalid_pin",
  "invalid_request",
  "signed_out",
  "device_revoked",
  "service_unavailable",
] as const;

// unexpected_response is never sent: the client raises it for an answer it cannot trust.
export type AuthStatus = (typeof AUTH_STATUSES)[number] | "unexpected_response";

const SUCCESS_STATUSES: readonly string[] = [
  "authenticated",
  "verification_required",
  "check_email",
  "code_verified",
  "signed_out",
  "device_revoked",
];

function isAuthBody(body: unknown): body is AuthResponse {
  return (
    typeof body === "object" &&
    body !== null &&
    (AUTH_STATUSES as readonly unknown[]).includes(
      (body as { status?: unknown }).status,
    )
  );
}

export interface AuthRequest {
  email?: string;
  phoneNumber?: string;
  pin?: string;
  deviceId?: string;
  code?: string;
  refreshToken?: string;
  // Web only: whether the browser keeps this device trusted after it closes.
  rememberDevice?: boolean;
}

export interface AuthResponse {
  status: AuthStatus;
  accessToken?: string | null;
  refreshToken?: string | null;
  retryAfterSeconds?: number | null;
  developmentCode?: string | null;
  maskedEmail?: string | null;
  // With invalid_pin: the shortest new PIN the organization accepts.
  minimumPinLength?: number | null;
}

export interface PersonIdentity {
  firstName: string;
  lastName: string;
  role: string;
  permissions: string[];
}

export interface AuthenticatedPerson extends PersonIdentity {
  userId: string;
}

export interface SessionTokens {
  accessToken: string;
  refreshToken: string;
}

export type AuthOperation =
  | "sign-in"
  | "verify-device"
  | "setup-pin/request"
  | "setup-pin/verify"
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
          ? pinHelp(response.minimumPinLength ?? undefined)
          : response.status === "unexpected_response"
            ? "The service answered in a way this app does not understand. Try again shortly."
            : httpStatus === 429
              ? "Too many requests. Please wait a minute."
              : httpStatus >= 500
                ? "The service is not available right now. Try again shortly."
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
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok)
      throw new AuthError(
        isAuthBody(body) ? body : { status: "authentication_failed" },
        response.status,
      );
    if (!isAuthBody(body) || !SUCCESS_STATUSES.includes(body.status))
      throw new AuthError({ status: "unexpected_response" }, response.status);
    return body;
  };
}

export function pauseSeconds(until: number, now = Date.now()): number {
  return Math.max(0, Math.ceil((until - now) / 1000));
}
