import { checkedFetch, SecurityCheckError } from "./checkedFetch";
import { clearDataCache } from "./data/cache";

const SESSION_EXPIRED = "xcode:session-expired";

let refreshing: Promise<boolean> | null = null;

// One refresh at a time: concurrent requests that hit a 401 wait on the same attempt. A refresh that a security
// check intercepted never reached the server, so it is neither a success nor proof the session ended: it rejects
// instead of resolving false (which would sign the person out).
// Tabs share the refresh cookie, so they renew one at a time under a Web Lock: a tab that waited sends the cookie the
// one before it stored. Without Web Locks another tab may still renew first: the server then answers
// refresh_superseded, so the refresh is asked once more, after a moment for that tab's new cookie to land. A second
// loss ends the session.
const askRefresh = () =>
  checkedFetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });

const superseded = async (response: Response) =>
  response.status === 401 &&
  (await response.json().catch(() => null))?.status === "refresh_superseded";

const REFRESH_LOCK = "xcode:refresh";
const SUPERSEDED_WAIT_MS = 300;

function oneTabAtATime<T>(run: () => Promise<T>): Promise<T> {
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
  return locks ? locks.request(REFRESH_LOCK, run) : run();
}

async function renew() {
  const response = await askRefresh();
  if (response.ok) return true;
  if (!(await superseded(response))) return false;
  await new Promise((resolve) => setTimeout(resolve, SUPERSEDED_WAIT_MS));
  return (await askRefresh()).ok;
}

function refreshSession() {
  refreshing ??= oneTabAtATime(renew)
    .catch((error) => {
      if (error instanceof SecurityCheckError) throw error;
      return false;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function fetchRefreshingOnce(input: string, init?: RequestInit) {
  const response = await checkedFetch(input, init);
  if (response.status !== 401 || !(await refreshSession())) return response;
  return checkedFetch(input, init);
}

// Access tokens are short-lived. On a 401, refresh the session once and retry; if that
// fails too, tell the app the session has ended.
export async function fetchWithSession(input: string, init?: RequestInit) {
  const response = await fetchRefreshingOnce(input, init);
  if (response.status === 401) {
    clearDataCache();
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  }
  return response;
}

// On page load: whether the browser still holds a session (refreshing an expired access
// token if needed). Having none is normal here, so nothing is announced.
export async function restoreSession() {
  try {
    return (await fetchRefreshingOnce("/api/auth/session")).ok;
  } catch {
    return false;
  }
}

// The signed-in person, or null without a session: the sign-in screens greet them by name when the PIN is asked
// again after a while without activity.
export async function readSession(): Promise<{
  firstName: string;
  lastName: string;
  role: string;
} | null> {
  try {
    const response = await fetchRefreshingOnce("/api/auth/session");
    if (!response.ok) return null;
    const session = (await response.json()) as {
      firstName?: string;
      lastName?: string;
      role?: string;
    };
    return {
      firstName: session.firstName ?? "",
      lastName: session.lastName ?? "",
      role: session.role ?? "",
    };
  } catch {
    return null;
  }
}

export function onSessionExpired(listener: () => void) {
  window.addEventListener(SESSION_EXPIRED, listener);
  return () => window.removeEventListener(SESSION_EXPIRED, listener);
}
