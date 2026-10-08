import {
  CODE_TRIES,
  codeOutcome,
  createAttempts,
  outcomeOf,
  triesLeft,
  wrongCodeMessage,
  wrongPinMessage,
  type OfflineStore,
} from "../src/auth/attempts";
import type { OfflineTries } from "../src/lib/storage";

const limits = { triesAllowed: 5, lockoutSeconds: 900 };

// A store whose reads and writes take a few turns of the event loop, as the keychain does.
function slowStore(start: OfflineTries = { count: 0, pausedUntil: 0 }) {
  const state = { saved: start, writes: 0 };
  const turn = () => new Promise((resolve) => setTimeout(resolve, 5));
  const store: OfflineStore = {
    async load() {
      await turn();
      return { ...state.saved };
    },
    async save(tries) {
      await turn();
      state.saved = { ...tries };
      state.writes += 1;
    },
  };
  return { store, state };
}

describe("messages", () => {
  it.each([
    [1, "1 try left"],
    [2, "2 tries left"],
    [4, "4 tries left"],
  ])("says %i as %s", (left, text) => {
    expect(triesLeft(left)).toBe(text);
    expect(wrongPinMessage(left)).toBe(`Wrong PIN. ${text}.`);
    expect(wrongCodeMessage(left)).toBe(`That code is wrong. ${text}.`);
  });
});

describe("outcomeOf", () => {
  it("counts down the tries before the limit", () => {
    expect(outcomeOf(1, limits)).toEqual({
      kind: "left",
      left: 4,
      message: "Wrong PIN. 4 tries left.",
    });
    expect(outcomeOf(4, limits)).toMatchObject({ kind: "left", left: 1 });
  });

  it("pauses at the limit for the whole lockout", () => {
    expect(outcomeOf(5, limits, 1_000)).toEqual({
      kind: "paused",
      until: 901_000,
    });
    expect(outcomeOf(9, limits, 0)).toEqual({ kind: "paused", until: 900_000 });
  });
});

describe("codeOutcome", () => {
  it("kills the code at the fifth wrong try", () => {
    expect(codeOutcome(1)).toEqual({
      dead: false,
      message: "That code is wrong. 4 tries left.",
    });
    expect(codeOutcome(CODE_TRIES - 1).dead).toBe(false);
    expect(codeOutcome(CODE_TRIES)).toEqual({
      dead: true,
      message: "Too many wrong codes. Tap Send a new code.",
    });
  });
});

describe("online tries", () => {
  it("count for each number and pause at the limit", () => {
    const attempts = createAttempts(slowStore().store);
    for (let i = 1; i < 5; i++)
      expect(attempts.wrongOnline("0733520614", limits)).toMatchObject({
        kind: "left",
        left: 5 - i,
      });
    expect(attempts.wrongOnline("0712345678", limits)).toMatchObject({
      left: 4,
    });
    expect(attempts.wrongOnline("0733520614", limits).kind).toBe("paused");
  });

  it("start again after a clear", async () => {
    const attempts = createAttempts(slowStore().store);
    attempts.wrongOnline("0733520614", limits);
    attempts.wrongOnline("0733520614", limits);
    await attempts.clear("0733520614");
    expect(attempts.wrongOnline("0733520614", limits)).toMatchObject({
      left: 4,
    });
  });
});

describe("offline tries", () => {
  it("are kept between wrong PINs", async () => {
    const { store, state } = slowStore();
    const attempts = createAttempts(store);
    expect(await attempts.wrongOffline(limits)).toMatchObject({ left: 4 });
    expect(await attempts.wrongOffline(limits)).toMatchObject({ left: 3 });
    expect(state.saved).toEqual({ count: 2, pausedUntil: 0 });
  });

  it("store the pause and reset the count at the limit", async () => {
    const { store, state } = slowStore({ count: 4, pausedUntil: 0 });
    const outcome = await createAttempts(store).wrongOffline(limits);
    expect(outcome.kind).toBe("paused");
    expect(state.saved.count).toBe(0);
    expect(state.saved.pausedUntil).toBeGreaterThan(Date.now());
  });

  it("count two wrong PINs that overlap as two", async () => {
    const { store, state } = slowStore();
    const attempts = createAttempts(store);
    const [first, second] = await Promise.all([
      attempts.wrongOffline(limits),
      attempts.wrongOffline(limits),
    ]);
    expect(state.saved.count).toBe(2);
    expect([first, second]).toEqual([
      expect.objectContaining({ left: 4 }),
      expect.objectContaining({ left: 3 }),
    ]);
  });

  it("are not given back by a clear that was started later", async () => {
    const { store, state } = slowStore();
    const attempts = createAttempts(store);
    const wrong = attempts.wrongOffline(limits);
    const cleared = attempts.clear("0733520614");
    await Promise.all([wrong, cleared]);
    expect(state.saved).toEqual({ count: 0, pausedUntil: 0 });
  });

  it("are counted after a clear that was started earlier", async () => {
    const { store, state } = slowStore({ count: 3, pausedUntil: 0 });
    const attempts = createAttempts(store);
    const cleared = attempts.clear("0733520614");
    const wrong = attempts.wrongOffline(limits);
    await Promise.all([cleared, wrong]);
    expect(state.saved).toEqual({ count: 1, pausedUntil: 0 });
  });

  it("read a stored pause after the writes in front of it", async () => {
    const { store } = slowStore();
    const attempts = createAttempts(store);
    const until = Date.now() + 60_000;
    void attempts.wrongOffline({ triesAllowed: 1, lockoutSeconds: 60 });
    expect(await attempts.pausedUntil()).toBeGreaterThanOrEqual(until - 1000);
  });

  it("go on counting after a write fails", async () => {
    let failNext = true;
    const { store, state } = slowStore();
    const flaky: OfflineStore = {
      load: store.load,
      save: async (tries) => {
        if (failNext) {
          failNext = false;
          throw new Error("keychain unavailable");
        }
        await store.save(tries);
      },
    };
    const attempts = createAttempts(flaky);
    await expect(attempts.wrongOffline(limits)).rejects.toThrow("keychain");
    expect(await attempts.wrongOffline(limits)).toMatchObject({ left: 4 });
    expect(state.saved.count).toBe(1);
  });
});
