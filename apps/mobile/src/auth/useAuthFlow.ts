import { useMemo, useReducer } from "react";

import type { StoredPerson } from "../lib/storage";
import { useLatest } from "../lib/useLatest";
import { createAttempts } from "./attempts";
import { createAuthActions } from "./authActions";
import { initialState, reduce } from "./authFlowState";
import {
  useAlive,
  useDelayedSubmit,
  useOperationLock,
  usePause,
  useResendTimer,
} from "./hooks";

type Args = {
  trusted: StoredPerson | null;
  onSignedIn: (person: StoredPerson, offline: boolean) => void;
  onForgotten?: () => void;
};

// The auth state machine with its timers, the one-operation guard and the handlers that talk to the API.
export function useAuthFlow({ trusted, onSignedIn, onForgotten }: Args) {
  const [state, dispatch] = useReducer(reduce, trusted, initialState);
  const { busy, lock } = useOperationLock();
  const delayed = useDelayedSubmit();
  const alive = useAlive();
  const attempts = useMemo(() => createAttempts(), []);
  const latest = useLatest({ state, onSignedIn, onForgotten });

  const actions = useMemo(
    () =>
      createAuthActions({
        state: () => latest.current.state,
        dispatch,
        lock,
        delayed,
        attempts,
        alive,
        onSignedIn: (person, offline) =>
          latest.current.onSignedIn(person, offline),
        onForgotten: () => latest.current.onForgotten?.(),
      }),
    [latest, lock, delayed, attempts, alive],
  );

  const { screen } = state;
  usePause({
    until: screen.step === "paused" ? screen.until : null,
    hasTrusted: trusted !== null,
    attempts,
    dispatch,
    onEnded: actions.pauseEnded,
  });
  useResendTimer(screen.step === "code" ? screen.resendIn : 0, dispatch);

  return { state, busy, actions };
}
