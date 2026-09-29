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

export function pinHelp(minimumLength = 4): string {
  return minimumLength > 4
    ? `Use ${minimumLength}-8 digits, not all the same or an ascending/descending sequence.`
    : PIN_HELP;
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


export type RevenueStatus = "none" | "future" | "missing" | "amount" | "reason";

export interface RevenueCompanyOption {
  id: string;
  name: string;
}

export interface RevenueCell {
  date: string;
  status: RevenueStatus;
  expected: number;
  amount: number | null;
  reason: string | null;
  note: string | null;
  canEdit: boolean;
  editedAfterCapture: boolean;
  // The record's version, for a correction to send back; null when the day has no record.
  version?: number | null;
}

export interface RevenueVehicle {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  joinedOn: string;
  leftOn: string | null;
  earliestMissing: string | null;
  days: RevenueCell[];
  totalAmount: number;
  totalExpected: number;
  percent: number | null;
}

export interface RevenueWeek {
  weekStart: string;
  weekThrough: string;
  currentWeekStart: string;
  businessDate: string;
  companies: RevenueCompanyOption[];
  vehicles: RevenueVehicle[];
  totalAmount: number;
  totalExpected: number;
  percent: number | null;
}

// Each figure is null for a viewer who may not see the card it belongs to.
export interface RevenueDashboard {
  period: "today" | "week" | "month" | string;
  from: string;
  through: string;
  businessDate: string;
  revenue: number | null;
  expected: number | null;
  percent: number | null;
  capturedToday: number | null;
  vehiclesToday: number | null;
  missingDays: number | null;
  missingVehicles: number | null;
  editedRecords: number | null;
}

export interface SaveRevenue {
  amount: number | null;
  reason: string | null;
  note: string | null;
  // null for a new record; a correction sends the version it was read at.
  version?: number | null;
}
