import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
} from "react";

import { pauseSeconds } from "@xcode/shared/auth";

import { useLatest } from "../lib/useLatest";
import type { Attempts } from "./attempts";
import type { Action } from "./authFlowState";

// One network operation at a time. The ref is the guard, read at once; the state only tells the screen.
export type OperationLock = {
  acquire(): boolean;
  release(): void;
  held(): boolean;
};

export function useOperationLock(): { busy: boolean; lock: OperationLock } {
  const holding = useRef(false);
  const [busy, setBusy] = useState(false);
  const lock = useMemo<OperationLock>(
    () => ({
      acquire() {
        if (holding.current) return false;
        holding.current = true;
        setBusy(true);
        return true;
      },
      release() {
        holding.current = false;
        setBusy(false);
      },
      held: () => holding.current,
    }),
    [],
  );
  return { busy, lock };
}

// False once the screen is gone: a finished call then neither signs anyone in nor shows a message.
export function useAlive(): () => boolean {
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  return useCallback(() => alive.current, []);
}

export type DelayedSubmit = {
  schedule(run: () => void): void;
  // True when a submit was waiting and has been dropped.
  cancel(): boolean;
};

// The pad waits a moment after the last number so the dots can fill before the entry is checked.
export function useDelayedSubmit(delay = 180): DelayedSubmit {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  return useMemo<DelayedSubmit>(
    () => ({
      schedule(run) {
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => {
          timer.current = null;
          run();
        }, delay);
      },
      cancel() {
        const waiting = timer.current !== null;
        if (timer.current) clearTimeout(timer.current);
        timer.current = null;
        return waiting;
      },
    }),
    [delay],
  );
}

export function useResendTimer(resendIn: number, dispatch: Dispatch<Action>) {
  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = setTimeout(() => dispatch({ type: "resendTick" }), 1000);
    return () => clearTimeout(timer);
  }, [resendIn, dispatch]);
}

type PauseArgs = {
  // When the pause on screen ends, or null while there is none.
  until: number | null;
  // A trusted phone keeps a pause from offline PINs across restarts.
  hasTrusted: boolean;
  attempts: Attempts;
  dispatch: Dispatch<Action>;
  onEnded: () => void;
};

export function usePause({
  until,
  hasTrusted,
  attempts,
  dispatch,
  onEnded,
}: PauseArgs) {
  const ended = useLatest(onEnded);

  useEffect(() => {
    if (until === null) return;
    const tick = () => {
      const now = Date.now();
      dispatch({ type: "pauseTick", now });
      if (pauseSeconds(until, now) <= 0) {
        clearInterval(timer);
        ended.current();
      }
    };
    const timer = setInterval(tick, 1000);
    tick();
    return () => clearInterval(timer);
  }, [until, dispatch, ended]);

  useEffect(() => {
    if (!hasTrusted) return;
    let live = true;
    void attempts.pausedUntil().then((paused) => {
      const now = Date.now();
      if (live && paused > now)
        dispatch({ type: "paused", until: paused, now });
    });
    return () => {
      live = false;
    };
  }, [hasTrusted, attempts, dispatch]);
}
