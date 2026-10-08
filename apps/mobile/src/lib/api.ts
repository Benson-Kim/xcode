import { Platform } from "react-native";

import {
  AuthError,
  createAuthClient,
  type AuthOperation,
  type AuthRequest,
  type AuthResponse,
} from "@xcode/shared/auth";

import {
  forgetPerson,
  getDeviceId,
  loadSession,
  saveSession,
  type StoredSession,
} from "./storage";

const fallbackUrl =
  Platform.OS === "android" ? "http://10.0.2.2:5000" : "http://localhost:5000";

export const apiUrl = (() => {
  const url = process.env.EXPO_PUBLIC_API_URL || (__DEV__ ? fallbackUrl : "");
  if (!url)
    throw new Error("EXPO_PUBLIC_API_URL must be set for release builds.");
  if (!__DEV__ && !url.startsWith("https://"))
    throw new Error("EXPO_PUBLIC_API_URL must use HTTPS in release builds.");
  return url;
})();

// The API could not be reached. Unlock falls back to the phone's own PIN check.
export class OfflineError extends Error {
  constructor() {
    super("No internet connection.");
  }
}

// The API answered with a failure that is not the person's to fix. Treated as unreachable.
export class ServerError extends OfflineError {
  constructor() {
    super();
    this.message = "Something went wrong on the server. Try again in a moment.";
  }
}

// The session can no longer be renewed, so the person has to sign in again.
export class SessionEndedError extends Error {
  constructor() {
    super("Your session has ended. Sign in again.");
  }
}

const REQUEST_TIMEOUT_MS = 15_000;

// A hung connection is as good as none: the request is abandoned after the timeout.
async function reach(input: RequestInfo | URL, init?: RequestInit) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const caller = init?.signal;
  if (caller) {
    if (caller.aborted) controller.abort();
    else
      caller.addEventListener("abort", () => controller.abort(), {
        once: true,
      });
  }
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch {
    throw new OfflineError();
  } finally {
    clearTimeout(timer);
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
    // Every sign-in and every renewal passes through here, so this is the last time the phone reached
    // the server: what the 72-hour offline unlock window is measured from (D7).
    lastOnlineAt: Date.now(),
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
      if (!(error instanceof AuthError)) throw error;
      throw error.httpStatus === 401 || error.httpStatus === 403
        ? new SessionEndedError()
        : new ServerError();
    }
  })().finally(() => {
    renewing = null;
  });
  return renewing;
}

// A request as the signed-in person. An expired access token is renewed once; a session that cannot be renewed ends.
async function authorized(path: string, init: RequestInit = {}) {
  const session = await loadSession();
  if (!session) throw new SessionEndedError();
  const call = (token: string) =>
    reach(`${apiUrl}/${path}`, {
      ...init,
      headers: {
        ...(init.headers as Record<string, string>),
        Authorization: `Bearer ${token}`,
      },
    });
  let response = await call(session.accessToken);
  if (response.status === 401)
    response = await call((await renew()).accessToken);
  if (response.status === 401) throw new SessionEndedError();
  return response;
}

// GET from the API as the signed-in person (path relative to the API, for example "auth/session").
export async function apiGet<T>(path: string): Promise<T> {
  const response = await authorized(path);
  const body = await response.json().catch(() => ({}));
  // The API's detail says what to fix; its title is only the category. A server failure has nothing to fix on the phone.
  if (response.status >= 500) throw new ServerError();
  if (!response.ok)
    throw new Error(
      body.detail || body.title || "The request could not be completed.",
    );
  return body as T;
}

// PUT JSON as the signed-in person and return the status with the body, whatever the outcome, for callers
// that act on a 400, 403, 404 or 409 themselves. Only no connection or an ended session throws.
export async function apiPutResult<T>(
  path: string,
  body: unknown,
): Promise<{ status: number; body: T }> {
  const response = await authorized(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return {
    status: response.status,
    body: (await response.json().catch(() => ({}))) as T,
  };
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
