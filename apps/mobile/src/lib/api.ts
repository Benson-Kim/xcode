import { Platform } from "react-native";
import {
  AuthError,
  createAuthClient,
  type AuthOperation,
  type AuthRequest,
  type AuthResponse,
} from "@xcode/shared";
import {
  forgetPerson,
  getDeviceId,
  loadSession,
  saveSession,
  type StoredSession,
} from "./storage";

export const apiUrl =
  process.env.EXPO_PUBLIC_API_URL ||
  (Platform.OS === "android"
    ? "http://10.0.2.2:5000"
    : "http://localhost:5000");

// The API could not be reached. Unlock falls back to the phone's own PIN check.
export class OfflineError extends Error {
  constructor() {
    super("No internet connection.");
  }
}

// The session can no longer be renewed, so the person has to sign in again.
export class SessionEndedError extends Error {
  constructor() {
    super("Your session has ended. Sign in again.");
  }
}

async function reach(input: RequestInfo | URL, init?: RequestInit) {
  try {
    return await fetch(input, init);
  } catch {
    throw new OfflineError();
  }
}

const authClient = createAuthClient(`${apiUrl}/auth`, reach as typeof fetch);

// The API rejects a request with any field missing, so every call sends them all.
export async function authApi(
  operation: AuthOperation | "revoke-device",
  request: AuthRequest = {},
): Promise<AuthResponse> {
  const deviceId = await getDeviceId();
  const session = await loadSession();
  return authClient(
    operation === "revoke-device"
      ? `devices/${encodeURIComponent(deviceId)}/revoke`
      : operation,
    {
      email: "",
      phoneNumber: "",
      pin: "",
      code: "",
      ...request,
      deviceId,
      refreshToken: session?.refreshToken || "",
    },
    session?.accessToken,
  );
}

// Keeps the tokens from an authenticated response for the number that signed in.
export async function keepSession(
  phoneNumber: string,
  result: AuthResponse,
): Promise<StoredSession> {
  const session = {
    phoneNumber,
    accessToken: result.accessToken || "",
    refreshToken: result.refreshToken || "",
  };
  await saveSession(session);
  return session;
}

let renewing: Promise<StoredSession> | null = null;

// Access tokens last minutes. One renewal at a time: concurrent requests wait on the same attempt.
function renew() {
  renewing ??= (async () => {
    const session = await loadSession();
    if (!session) throw new SessionEndedError();
    try {
      const result = await authApi("refresh");
      if (result.status !== "authenticated" || !result.accessToken)
        throw new SessionEndedError();
      return await keepSession(session.phoneNumber, result);
    } catch (error) {
      throw error instanceof AuthError ? new SessionEndedError() : error;
    }
  })().finally(() => {
    renewing = null;
  });
  return renewing;
}

// GET from the API as the signed-in person (path relative to the API, for example "auth/session").
export async function apiGet<T>(path: string): Promise<T> {
  const session = await loadSession();
  if (!session) throw new SessionEndedError();
  const call = (token: string) =>
    reach(`${apiUrl}/${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  let response = await call(session.accessToken);
  if (response.status === 401)
    response = await call((await renew()).accessToken);
  if (response.status === 401) throw new SessionEndedError();
  const body = await response.json().catch(() => ({}));
  // The API's detail says what to fix; its title is only the category.
  if (!response.ok)
    throw new Error(
      body.detail || body.title || "The request could not be completed.",
    );
  return body as T;
}

// Switch user: stop trusting this phone for the person (their refresh tokens go with it), then everything kept for them on the phone is removed.
// Offline, the phone forgets them anyway and the trust ends when the admin revokes it or it expires.
export async function forgetThisPhone(): Promise<void> {
  try {
    await authApi("revoke-device").catch(async (error) => {
      if (!(error instanceof AuthError) || error.httpStatus !== 401)
        throw error;
      await renew();
      await authApi("revoke-device");
    });
  } catch {
    await authApi("sign-out").catch(() => undefined);
  }
  await forgetPerson();
}
