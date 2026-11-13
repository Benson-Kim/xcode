import { useEffect, useRef } from "react";
import { AppState } from "react-native";

import { SessionEndedError, apiGet } from "./api";

export const SESSION_CHECK_INTERVAL_MS = 30_000;

// The server ends a person's sessions when their email changes, and the phone otherwise learns it on its next request.
// Each time the app comes back to the front the session is asked about, at most once every 30 seconds, through the
// normal client (so an expired access token is renewed first). Only a session the server ended signs the person out:
// no connection or a server fault changes nothing, and nothing is asked while the phone is known to be offline.
export function useSessionCheck(offline: boolean, onSessionEnded: () => void) {
  const state = useRef({ offline, onSessionEnded });
  useEffect(() => {
    state.current = { offline, onSessionEnded };
  });

  useEffect(() => {
    let last = Number.NEGATIVE_INFINITY;
    let active = true;
    const listener = AppState.addEventListener("change", (next) => {
      if (next !== "active" || state.current.offline) return;
      const now = Date.now();
      if (now - last < SESSION_CHECK_INTERVAL_MS) return;
      last = now;
      apiGet("auth/session").catch((error: unknown) => {
        if (active && error instanceof SessionEndedError)
          state.current.onSessionEnded();
      });
    });
    return () => {
      active = false;
      listener.remove();
    };
  }, []);
}
