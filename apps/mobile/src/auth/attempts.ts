import {
  forgetPinCheck,
  loadOfflineTries,
  saveOfflineTries,
  type OfflineTries,
} from "../lib/storage";

export type TryLimits = { triesAllowed: number; lockoutSeconds: number };

export const triesLeft = (left: number) =>
  `${left} ${left === 1 ? "try" : "tries"} left`;
export const wrongPinMessage = (left: number) =>
  `Wrong PIN. ${triesLeft(left)}.`;
export const wrongCodeMessage = (left: number) =>
  `That code is wrong. ${triesLeft(left)}.`;
export const GONE_CODE_MESSAGE =
  "This code no longer works. Tap Send a new code.";
export const RESENT_CODE_MESSAGE =
  "That code was wrong 3 times, so we emailed you a new one.";

// A code the server refused, from the tries it says are left: none left means the code expired or was replaced.
export function refusedCode(left: number | null | undefined): {
  dead: boolean;
  message: string;
} {
  return typeof left === "number" && left > 0
    ? { dead: false, message: wrongCodeMessage(left) }
    : { dead: true, message: GONE_CODE_MESSAGE };
}

export type Outcome =
  | { kind: "left"; left: number; message: string }
  | { kind: "paused"; until: number };

// What the count of wrong PINs means: a pause once the organization's limit is reached.
export function outcomeOf(
  count: number,
  limits: TryLimits,
  now = Date.now(),
): Outcome {
  if (count >= limits.triesAllowed)
    return { kind: "paused", until: now + limits.lockoutSeconds * 1000 };
  const left = limits.triesAllowed - count;
  return { kind: "left", left, message: wrongPinMessage(left) };
}

export type OfflineStore = {
  load(): Promise<OfflineTries>;
  save(tries: OfflineTries): Promise<void>;
  forgetCheck(): Promise<void>;
};

const phoneStore: OfflineStore = {
  load: () => loadOfflineTries(),
  save: (tries) => saveOfflineTries(tries),
  forgetCheck: () => forgetPinCheck(),
};

// The stored count is read, changed and written back. One at a time, or two wrong PINs count as one.
let tail: Promise<unknown> = Promise.resolve();
function serialized<T>(task: () => Promise<T>): Promise<T> {
  const run = tail.then(() => task());
  tail = run.catch(() => undefined);
  return run;
}

export type Attempts = {
  // Wrong PINs the server refused, counted in memory for each number.
  wrongOnline(phone: string, limits: TryLimits): Outcome;
  // Wrong PINs checked on the phone itself, kept so a restart does not give the tries back. At the limit the phone's
  // PIN check is deleted.
  wrongOffline(limits: TryLimits): Promise<Outcome>;
  pausedUntil(): Promise<number>;
  clear(phone: string): Promise<void>;
};

export function createAttempts(store: OfflineStore = phoneStore): Attempts {
  const online = new Map<string, number>();
  return {
    wrongOnline(phone, limits) {
      const count = (online.get(phone) ?? 0) + 1;
      online.set(phone, count);
      return outcomeOf(count, limits);
    },
    wrongOffline: (limits) =>
      serialized(async () => {
        const outcome = outcomeOf((await store.load()).count + 1, limits);
        if (outcome.kind === "paused") await store.forgetCheck();
        await store.save(
          outcome.kind === "paused"
            ? { count: 0, pausedUntil: outcome.until }
            : { count: limits.triesAllowed - outcome.left, pausedUntil: 0 },
        );
        return outcome;
      }),
    pausedUntil: () => serialized(async () => (await store.load()).pausedUntil),
    clear(phone) {
      online.set(phone, 0);
      return serialized(() => store.save({ count: 0, pausedUntil: 0 }));
    },
  };
}
