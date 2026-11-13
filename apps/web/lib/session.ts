import { checkedFetch } from "./checkedFetch";
import { clearDataCache } from "./data/cache";

const SESSION_EXPIRED = "xcode:session-expired";

let refreshing: Promise<boolean> | null = null;

// One refresh at a time: concurrent requests that hit a 401 wait on the same attempt. Only the server's answer
// decides: a refresh that got none (the network failed, or a security check intercepted it) is neither a success nor
// proof the session ended, so it rejects instead of resolving false (which would sign the person out).
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
  refreshing ??= oneTabAtATime(renew).finally(() => {
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

export const SESSION_CHECK_INTERVAL_MS = 30_000;

// A session the server ended (an email change, a removal) is otherwise noticed only on the next request. When the tab
// comes back into view the session is asked about, at most once every 30 seconds. A 401 that a refresh cannot mend
// runs the usual signed-out path through fetchWithSession; a network error or a blocked check changes nothing.
export function watchSession(now: () => number = Date.now) {
  let last = Number.NEGATIVE_INFINITY;
  const check = () => {
    if (document.visibilityState === "hidden") return;
    const time = now();
    if (time - last < SESSION_CHECK_INTERVAL_MS) return;
    last = time;
    void fetchWithSession("/api/auth/session").catch(() => undefined);
  };
  document.addEventListener("visibilitychange", check);
  window.addEventListener("focus", check);
  return () => {
    document.removeEventListener("visibilitychange", check);
    window.removeEventListener("focus", check);
  };
}

export function onSessionExpired(listener: () => void) {
  window.addEventListener(SESSION_EXPIRED, listener);
  return () => window.removeEventListener(SESSION_EXPIRED, listener);
}
