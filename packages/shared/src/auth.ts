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
  // The number-first routes (XCODE Web v2.33): the next step after a number, the PIN lock, a blocked person, the
  // third wrong code and a changed PIN.
  "pin_required",
  "pin_locked",
  "blocked",
  "code_resent",
  "pin_changed",
  // A refresh token replayed within 30 seconds of its rotation on the same device: another request already
  // renewed the session. Nothing is revoked.
  "refresh_superseded",
  // HTTP 426: the mobile app's version (X-XCODE-Client) is below the minimum the API supports.
  "update_required",
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
  "pin_required",
  "code_resent",
  "pin_changed",
];

// What a code was sent for: confirming a new device, the first sign in, or a PIN reset.
export type CodePurpose = "new_device" | "first_setup" | "pin_reset";

// Why a new PIN was refused.
export type PinProblem = "length" | "weak" | "unchanged";

// Why a matching invitation link and number were refused. An unknown link, a wrong number or another person's
// link carry no problem at all, so they cannot be told apart.
export type InviteProblem = "expired" | "used" | "revoked";

const INVITE_TOKEN = /^[A-Za-z0-9_-]{43}$/;

// The link token of an invitation: 32 random bytes in base64url.
export function isInviteToken(value: unknown): value is string {
  return typeof value === "string" && INVITE_TOKEN.test(value);
}

export function inviteProblemText(
  problem: InviteProblem | null | undefined,
): string {
  if (problem === "expired")
    return "This invitation has expired. Ask the office to send it again.";
  if (problem === "used")
    return "This invitation has been used. Sign in with your number and PIN.";
  if (problem === "revoked")
    return "This invitation is no longer valid. Ask the office for a new one.";
  return "This number does not match the invitation. Check it, or open the link in your latest invitation email.";
}

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
  // The number-first routes: the trusted-device token, the device's name, what a code is for, whether to trust
  // the device after a code, and the current and new PIN of a change.
  deviceToken?: string;
  deviceName?: string;
  purpose?: CodePurpose;
  trustDevice?: boolean;
  currentPin?: string;
  newPin?: string;
  // Web only, on a trusted-device remove: the row is this browser, so it forgets its own trust.
  thisDevice?: boolean;
  // invite/redeem: the link token from the invitation email.
  token?: string;
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
  // The step envelope of the number-first routes.
  purpose?: CodePurpose | null;
  triesLeft?: number | null;
  pinProblem?: PinProblem | null;
  deviceToken?: string | null;
  // invite/redeem: the code it minted (the web proxy keeps it in a cookie), and why a matching link was refused.
  code?: string | null;
  inviteProblem?: InviteProblem | null;
  // start: no code was sent because the first-setup code is in the invitation email.
  invitation?: boolean | null;
}

// A device the person trusts (GET /auth/trusted-devices).
export interface TrustedDevice {
  id: string;
  name: string | null;
  trustedAt: string;
  lastUsedAt: string | null;
  thisDevice: boolean;
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
  | "sign-out"
  // The number-first routes of XCODE Web v2.33.
  | "start"
  | "pin"
  | "code"
  | "code/resend"
  | "pin/forgot"
  | "pin/new"
  | "pin/change"
  | "invite/redeem";

// The prototype's words for a refused new PIN.
export function pinProblemText(
  problem: PinProblem | null | undefined,
  changing = false,
): string {
  if (problem === "length") return "The PIN is 4 digits.";
  if (problem === "unchanged")
    return changing
      ? "Choose a PIN different from the current one."
      : "Choose a PIN different from the old one.";
  return "Choose a PIN that is harder to guess.";
}

export class AuthError extends Error {
  constructor(
    public readonly response: AuthResponse,
    public readonly httpStatus: number,
  ) {
    super(
      response.status === "paused"
        ? "Sign-in is paused. Try again when the timer ends, or reset your PIN."
        : response.status === "pin_locked"
          ? "Too many wrong PINs. Reset your PIN to sign in."
          : response.status === "blocked"
            ? "This number is blocked. Speak to the office."
            : response.status === "invalid_pin" && response.pinProblem
              ? pinProblemText(response.pinProblem)
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
    operation:
      | AuthOperation
      | `devices/${string}/revoke`
      | `trusted-devices/${string}/remove`,
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
