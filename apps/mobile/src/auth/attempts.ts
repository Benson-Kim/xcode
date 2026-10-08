import {
  loadOfflineTries,
  saveOfflineTries,
  type OfflineTries,
} from "../lib/storage";

export const CODE_TRIES = 5;

export type TryLimits = { triesAllowed: number; lockoutSeconds: number };

export const triesLeft = (left: number) =>
  `${left} ${left === 1 ? "try" : "tries"} left`;
export const wrongPinMessage = (left: number) =>
  `Wrong PIN. ${triesLeft(left)}.`;
export const wrongCodeMessage = (left: number) =>
  `That code is wrong. ${triesLeft(left)}.`;
export const DEAD_CODE_MESSAGE = "Too many wrong codes. Tap Send a new code.";

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

export function codeOutcome(wrong: number): { dead: boolean; message: string } {
  return wrong >= CODE_TRIES
    ? { dead: true, message: DEAD_CODE_MESSAGE }
    : { dead: false, message: wrongCodeMessage(CODE_TRIES - wrong) };
}

export type OfflineStore = {
  load(): Promise<OfflineTries>;
  save(tries: OfflineTries): Promise<void>;
};

const phoneStore: OfflineStore = {
  load: () => loadOfflineTries(),
  save: (tries) => saveOfflineTries(tries),
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
  // Wrong PINs checked on the phone itself, kept so a restart does not give the tries back.
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
