import { checkedFetch, SecurityCheckError } from "./checkedFetch";
import { clearDataCache } from "./data/cache";

const SESSION_EXPIRED = "xcode:session-expired";

let refreshing: Promise<boolean> | null = null;

// One refresh at a time: concurrent requests that hit a 401 wait on the same attempt. A refresh that a security
// check intercepted never reached the server, so it is neither a success nor proof the session ended: it rejects
// instead of resolving false (which would sign the person out).
function refreshSession() {
  refreshing ??= checkedFetch("/api/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  })
    .then((response) => response.ok)
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

export function onSessionExpired(listener: () => void) {
  window.addEventListener(SESSION_EXPIRED, listener);
  return () => window.removeEventListener(SESSION_EXPIRED, listener);
}
