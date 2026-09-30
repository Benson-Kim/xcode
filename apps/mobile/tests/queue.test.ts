import * as SecureStore from "expo-secure-store";
import { saveSession } from "../src/lib/storage";
import { QUEUE_LIMIT, QueueFullError, openQueue, type NewCapture, type QueueSnapshot } from "../src/revenue/queue";
import type { QueuedCapture } from "../src/revenue/types";
import { fakeApi } from "./fakeApi";

const OWNER = "0712345678";
const INDEX = `xcode.revenue-queue.${OWNER}`;
const items = () => require("expo-secure-store").__items as Map<string, string>;
const queueKeys = () => [...items().keys()].filter((key) => key.startsWith(INDEX));
const capture = (date: string, patch: Partial<NewCapture> = {}): NewCapture => ({
  vehicleId: "v-1",
  registration: "KDA 482M",
  date,
  amount: 1000,
  reason: null,
  note: null,
  version: null,
  ...patch,
});

function open() {
  const seen: QueueSnapshot[] = [];
  const queue = openQueue(OWNER, { onChange: (snapshot) => seen.push(snapshot), onSessionEnded: () => undefined });
  return { queue, latest: () => seen[seen.length - 1] };
}

beforeEach(async () => {
  await saveSession({ phoneNumber: OWNER, accessToken: "access-1", refreshToken: "refresh-1" });
});

const DAYS = ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29"];
type Answer = [status: number, body: unknown] | "offline";

// The API for every day of v-1 these tests capture: offline until a test says how it answers. reached lists what
// got an answer, so offline tries do not count as sent.
function revenueApi() {
  const api = fakeApi();
  const reached: { date: string; body: Record<string, string> }[] = [];
  let answer: (date: string) => Answer = () => "offline";
  for (const date of DAYS)
    api.on(`setup/revenue/v-1/${date}`, (body) => {
      const reply = answer(date);
      if (reply !== "offline") reached.push({ date, body });
      return reply;
    });
  return {
    reached,
    answer: (next: (date: string) => Answer) => void (answer = next),
  };
}

const summary = (entries: QueuedCapture[]) => entries.map((entry) => `${entry.date} ${entry.amount ?? entry.reason} ${entry.state}`);
const queueState = () => new Map(queueKeys().map((key) => [key, items().get(key)!]));

// Runs one operation and returns what the Keychain held for the queue before it and after each of its writes. The
// app can be killed at any of those points; a single Keychain write is all or nothing.
async function writePoints(operation: () => Promise<unknown>) {
  const set = jest.mocked(SecureStore.setItemAsync);
  const remove = jest.mocked(SecureStore.deleteItemAsync);
  const [setBefore, removeBefore] = [set.getMockImplementation()!, remove.getMockImplementation()!];
  const points = [queueState()];
  set.mockImplementation(async (...args) => {
    await setBefore(...args);
    points.push(queueState());
  });
  remove.mockImplementation(async (...args) => {
    await removeBefore(...args);
    points.push(queueState());
  });
  try {
    await operation();
  } finally {
    set.mockImplementation(setBefore);
    remove.mockImplementation(removeBefore);
  }
  return points;
}

// The app starting again at one of those points: the queue's keys as they were then, the session as it is.
function restartAt(point: Map<string, string>) {
  for (const key of queueKeys()) items().delete(key);
  for (const [key, value] of point) items().set(key, value);
  return open();
}

// Captures for the 25th and 27th in slots 0 and 2, with slot 1 free between them.
async function withHole() {
  const api = revenueApi();
  const first = open();
  for (const date of ["2026-09-25", "2026-09-26", "2026-09-27"]) await first.queue.add(capture(date));
  await first.queue.discard(first.latest().entries[1]);
  await first.queue.sync();
  expect(JSON.parse(items().get(INDEX)!)).toEqual({ used: "101" });
  return { api, ...first };
}

it("sends an earlier day first even when it was kept after a later one, and a newer capture replaces the waiting one", async () => {
  const api = fakeApi();
  let online = false;
  const order: string[] = [];
  for (const path of ["v-1/2026-09-27", "v-1/2026-09-28", "v-1/2026-09-29", "v-2/2026-09-28"])
    api.on(`setup/revenue/${path}`, () => (online ? (order.push(path), [200, { id: path, version: 1 }]) : "offline"));
  const { queue, latest } = open();

  await queue.add(capture("2026-09-29"));
  await queue.add(capture("2026-09-27", { version: 4 }));
  await queue.add(capture("2026-09-28", { vehicleId: "v-2", registration: "KCY 117T" }));
  await queue.add(capture("2026-09-28"));
  await queue.add(capture("2026-09-28", { amount: 1200 }));
  await queue.sync();
  expect(latest().entries.map((entry) => `${entry.vehicleId}/${entry.date}`)).toEqual(["v-1/2026-09-27", "v-2/2026-09-28", "v-1/2026-09-28", "v-1/2026-09-29"]);

  online = true;
  await queue.sync();
  expect(order.filter((path) => path.startsWith("v-1"))).toEqual(["v-1/2026-09-27", "v-1/2026-09-28", "v-1/2026-09-29"]);
  expect(order).toHaveLength(4);
  // A correction sends the version it was read at; a new day sends null; the replaced capture went once, as 1200.
  expect(api.sent("setup/revenue/v-1/2026-09-27").at(-1)).toEqual({ amount: 1000, reason: null, note: null, version: 4 });
  expect(api.sent("setup/revenue/v-1/2026-09-28").at(-1)).toEqual({ amount: 1200, reason: null, note: null, version: null });
  expect(api.calls.filter((call) => call.path === "setup/revenue/v-1/2026-09-28" && call.body.amount === (1000 as unknown as string))).toHaveLength(0);
  expect(latest().entries).toEqual([]);
  expect(queueKeys().filter((key) => items().get(key) !== JSON.stringify({ used: "" }))).toEqual([]);
});

it("keeps every refused capture with the reason, and drops one only on a 200 or the person's discard", async () => {
  const api = fakeApi();
  api.on("setup/revenue/v-1/2026-09-25", [403, { title: "Not permitted in this organization or data scope.", detail: "Correcting a past day needs Correct revenue after the day." }]);
  api.on("setup/revenue/v-1/2026-09-26", [404, {}]);
  api.on("setup/revenue/v-1/2026-09-27", [400, { title: "Invalid setup change", detail: "Record 2026-09-20 before this date first.", earliestMissing: "2026-09-20" }]);
  api.on("setup/revenue/v-1/2026-09-28", [503, {}]);
  api.on("setup/revenue/v-1/2026-09-29", "offline");
  const { queue, latest } = open();
  for (const date of ["2026-09-25", "2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29"]) await queue.add(capture(date));
  await queue.sync();

  const byDate = Object.fromEntries(latest().entries.map((entry) => [entry.date, entry]));
  expect(byDate["2026-09-25"]).toMatchObject({ state: "failed", message: "Correcting a past day needs Correct revenue after the day." });
  expect(byDate["2026-09-26"]).toMatchObject({ state: "failed", message: "This vehicle is no longer in your view." });
  expect(byDate["2026-09-27"]).toMatchObject({ state: "blocked", message: "Capture 20 Sep 2026 first.", earliestMissing: "2026-09-20" });
  // The API struggling stops the round; later days wait and are not sent.
  expect(byDate["2026-09-28"]).toMatchObject({ state: "pending" });
  expect(byDate["2026-09-29"]).toMatchObject({ state: "pending" });
  expect(api.sent("setup/revenue/v-1/2026-09-29")).toHaveLength(0);
  expect(latest().entries).toHaveLength(5);

  // Failed entries wait for the person; a blocked one is tried again with every round.
  await queue.sync();
  expect(api.sent("setup/revenue/v-1/2026-09-25")).toHaveLength(1);
  expect(api.sent("setup/revenue/v-1/2026-09-27")).toHaveLength(2);

  await queue.discard(byDate["2026-09-26"]);
  expect(latest().entries.map((entry) => entry.date)).toEqual(["2026-09-25", "2026-09-27", "2026-09-28", "2026-09-29"]);
});

it("reads the queue back from the Keychain, clearing only corrupt entries", async () => {
  const api = fakeApi();
  api.on("setup/revenue/v-1/2026-09-28", "offline");
  api.on("setup/revenue/v-1/2026-09-29", "offline");
  const first = open();
  await first.queue.add(capture("2026-09-28"));
  await first.queue.add(capture("2026-09-29", { reason: "Other", amount: null, note: "Clutch failed on Thika Road" }));
  first.queue.close();

  // A tampered or truncated entry is removed rather than trusted.
  items().set(`xcode.revenue-queue.${OWNER}.0`, '{"vehicleId":"v-1","date":"2026-09-28","amount":-5');
  const again = open();
  await again.queue.ready;
  expect(again.latest().entries).toEqual([expect.objectContaining({ date: "2026-09-29", reason: "Other", note: "Clutch failed on Thika Road", state: "pending" })]);
  expect(items().has(`xcode.revenue-queue.${OWNER}.0`)).toBe(false);
  expect(JSON.parse(items().get(`xcode.revenue-queue.${OWNER}`)!)).toEqual({ used: "01" });
});

it("holds at most the queue limit with small Keychain values, and says so instead of losing the next capture", async () => {
  fakeApi().on("setup/revenue/v-1/2026-09-29", "offline");
  const { queue, latest } = open();
  const long = "é".repeat(80);
  for (let index = 0; index < QUEUE_LIMIT; index++)
    await queue.add(capture(new Date(Date.UTC(2025, 0, 1 + index)).toISOString().slice(0, 10), { amount: null, reason: "Other", note: long, vehicleId: "0b8f4c2e-5d1a-4e6b-9c3f-7a2d8e1f6b40" }));
  await expect(queue.add(capture("2026-09-29"))).rejects.toBeInstanceOf(QueueFullError);
  expect(latest().entries).toHaveLength(QUEUE_LIMIT);

  const bytes = (key: string) => new TextEncoder().encode(items().get(key)!).length;
  expect(bytes(`xcode.revenue-queue.${OWNER}`)).toBeLessThanOrEqual(QUEUE_LIMIT + 20);
  expect(Math.max(...queueKeys().map(bytes))).toBeLessThan(1024);
});

it("finds a capture the app kept but was killed before the index named, and never writes over it", async () => {
  const { api, queue } = await withHole();
  const points = await writePoints(() => queue.add(capture("2026-09-28", { amount: 1800 })));
  await settle(queue);
  // Killed between the capture's own write and the index's: slot 1 holds it and the index still says "101".
  const killed = points[1];
  expect(JSON.parse(killed.get(INDEX)!)).toEqual({ used: "101" });
  expect(JSON.parse(killed.get(`${INDEX}.1`)!)).toMatchObject({ date: "2026-09-28", amount: 1800 });

  const again = restartAt(killed);
  await again.queue.ready;
  expect(summary(again.latest().entries)).toEqual(["2026-09-25 1000 pending", "2026-09-27 1000 pending", "2026-09-28 1800 pending"]);
  // The next capture takes a free slot, not the one just found.
  await again.queue.add(capture("2026-09-29", { amount: 900 }));
  await again.queue.sync();
  again.queue.close();

  const last = open();
  await last.queue.ready;
  expect(summary(last.latest().entries)).toEqual(["2026-09-25 1000 pending", "2026-09-27 1000 pending", "2026-09-28 1800 pending", "2026-09-29 900 pending"]);
  api.answer(() => [200, { version: 1 }]);
  await last.queue.sync();
  expect(api.reached.map((sent) => sent.date)).toEqual(["2026-09-25", "2026-09-27", "2026-09-28", "2026-09-29"]);
  expect(api.reached[2].body).toEqual({ amount: 1800, reason: null, note: null, version: null });
  expect(last.latest().entries).toEqual([]);
});

// Every slot holding a capture is named by the index, one per vehicle and day shown.
function expectSlotsNamed(at: number, shown: number) {
  const named = [...(JSON.parse(items().get(INDEX) ?? '{"used":""}').used as string)].flatMap((bit, slot) => (bit === "1" ? [slot] : []));
  const slots = queueKeys().filter((key) => key !== INDEX).map((key) => Number(key.slice(INDEX.length + 1)));
  expect({ at, slots: slots.sort((a, b) => a - b) }).toEqual({ at, slots: named });
  expect({ at, slots: slots.length }).toEqual({ at, slots: shown });
}

// Starts the app again at every point an operation's writes can leave the Keychain in; expected[k] is what the queue
// shows after a start at point k. Each start takes a new capture without writing over anything, then, connected,
// sends each waiting capture once; conflicts and refusals wait for the person.
async function restartEach(api: ReturnType<typeof revenueApi>, points: Map<string, string>[], expected: string[][]) {
  expect(points).toHaveLength(expected.length);
  for (const [at, point] of points.entries()) {
    api.answer(() => "offline");
    const started = restartAt(point);
    await started.queue.ready;
    expect({ at, shown: summary(started.latest().entries) }).toEqual({ at, shown: expected[at] });
    expectSlotsNamed(at, expected[at].length);

    await started.queue.add(capture("2026-09-29", { amount: 700 }));
    await started.queue.sync();
    expect({ at, shown: summary(started.latest().entries) }).toEqual({ at, shown: [...expected[at], "2026-09-29 700 pending"] });
    expectSlotsNamed(at, expected[at].length + 1);

    const waiting = started.latest().entries.filter((entry) => entry.state === "pending" || entry.state === "blocked");
    const from = api.reached.length;
    api.answer(() => [200, { version: 1 }]);
    await started.queue.sync();
    await started.queue.sync();
    const bodies = waiting.map((entry) => ({ date: entry.date, body: { amount: entry.amount, reason: entry.reason, note: entry.note, version: entry.version } }));
    expect({ at, sent: api.reached.slice(from) }).toEqual({ at, sent: bodies });
    expect({ at, shown: summary(started.latest().entries) }).toEqual({ at, shown: expected[at].filter((line) => !line.endsWith("pending")) });
    started.queue.close();
  }
}

// Lets a round the operation started finish offline, so the closed queue sends nothing later.
async function settle(queue: ReturnType<typeof openQueue>) {
  await queue.sync();
  queue.close();
}

it("loses nothing and sends once wherever a new capture is cut short", async () => {
  const { api, queue } = await withHole();
  const points = await writePoints(() => queue.add(capture("2026-09-28", { amount: 1800 })));
  await settle(queue);
  // Its own slot, then the index.
  await restartEach(api, points, [
    ["2026-09-25 1000 pending", "2026-09-27 1000 pending"],
    ["2026-09-25 1000 pending", "2026-09-27 1000 pending", "2026-09-28 1800 pending"],
    ["2026-09-25 1000 pending", "2026-09-27 1000 pending", "2026-09-28 1800 pending"],
  ]);
});

it("keeps the waiting capture or its replacement, never both, wherever a newer capture of the day is cut short", async () => {
  const { api, queue } = await withHole();
  const points = await writePoints(() => queue.add(capture("2026-09-27", { amount: 1500 })));
  await settle(queue);
  // One write, in the waiting capture's slot.
  await restartEach(api, points, [
    ["2026-09-25 1000 pending", "2026-09-27 1000 pending"],
    ["2026-09-25 1000 pending", "2026-09-27 1500 pending"],
  ]);
});

it("keeps the capture wherever Replace with mine after a conflict is cut short, and sends it once more at most", async () => {
  const { api, queue, latest } = await withHole();
  const current = { date: "2026-09-25", status: "captured", amount: 2000, reason: null, note: null, version: 3 };
  api.answer((date) => (date === "2026-09-25" ? [409, { title: "Conflict", current }] : "offline"));
  await queue.sync();
  const conflict = latest().entries[0];
  expect(conflict).toMatchObject({ state: "conflict", current: { amount: 2000, version: 3 } });

  api.answer((date) => (date === "2026-09-25" ? [200, { version: 4 }] : "offline"));
  const points = await writePoints(() => queue.replace(conflict));
  await settle(queue);
  // The capture made pending over version 3, then, once the API accepted it, its slot emptied, then the index.
  expect(JSON.parse(points[1].get(`${INDEX}.0`)!)).toMatchObject({ state: "pending", version: 3 });
  // A start at point 1 may follow the API's 200: the capture goes once more, the API answers the identical replay
  // with 200 and changes nothing, and it leaves the phone. That repeat is the only one the queue allows.
  await restartEach(api, points, [
    ["2026-09-25 1000 conflict", "2026-09-27 1000 pending"],
    ["2026-09-25 1000 pending", "2026-09-27 1000 pending"],
    ["2026-09-27 1000 pending"],
    ["2026-09-27 1000 pending"],
  ]);
});

it("keeps what the API has not accepted wherever sending is cut short, and repeats only an accepted capture", async () => {
  const { api, queue } = await withHole();
  api.answer(() => [200, { version: 1 }]);
  const points = await writePoints(() => queue.sync());
  await settle(queue);
  // For each accepted capture: its slot emptied, then the index. A start at point 0 may follow the 200 for the
  // 25th, and at points 1 and 2 the 200 for the 27th: that capture goes once more, an identical replay the API
  // answers with 200 and changes nothing for.
  await restartEach(api, points, [
    ["2026-09-25 1000 pending", "2026-09-27 1000 pending"],
    ["2026-09-27 1000 pending"],
    ["2026-09-27 1000 pending"],
    [],
    [],
  ]);
});

it("keeps every other capture wherever a discard is cut short", async () => {
  const { api, queue, latest } = await withHole();
  api.answer((date) => (date === "2026-09-25" ? [403, { detail: "Correcting a past day needs Correct revenue after the day." }] : "offline"));
  await queue.sync();
  const refused = latest().entries[0];
  expect(refused).toMatchObject({ state: "failed" });
  api.answer(() => "offline");
  const points = await writePoints(() => queue.discard(refused));
  await settle(queue);
  await restartEach(api, points, [
    ["2026-09-25 1000 failed", "2026-09-27 1000 pending"],
    ["2026-09-27 1000 pending"],
    ["2026-09-27 1000 pending"],
  ]);
});

it("reads the index, each waiting capture and one free slot when it opens, and no more", async () => {
  const { queue } = await withHole();
  queue.close();
  const reads = jest.mocked(SecureStore.getItemAsync);
  reads.mockClear();
  const again = open();
  await again.queue.ready;
  expect(reads.mock.calls.map(([key]) => key)).toEqual([INDEX, `${INDEX}.0`, `${INDEX}.2`, `${INDEX}.1`]);
  again.queue.close();

  // A full queue has no free slot to read.
  items().set(INDEX, JSON.stringify({ used: "1".repeat(QUEUE_LIMIT) }));
  for (let slot = 0; slot < QUEUE_LIMIT; slot++) {
    const date = new Date(Date.UTC(2025, 0, 1 + slot)).toISOString().slice(0, 10);
    items().set(`${INDEX}.${slot}`, JSON.stringify({ ...capture(date), state: "pending", message: "", earliestMissing: null, current: null, queuedAt: slot }));
  }
  reads.mockClear();
  const full = open();
  await full.queue.ready;
  expect(reads).toHaveBeenCalledTimes(QUEUE_LIMIT + 1);
  expect(full.latest().entries).toHaveLength(QUEUE_LIMIT);
});

it("writes nothing more after a start that could not finish reading the queue back, so nothing it missed is lost", async () => {
  const kept = (date: string, queuedAt: number) => JSON.stringify({ ...capture(date), state: "pending", message: "", earliestMissing: null, current: null, queuedAt });
  const start = (stored: [string, string][]) => {
    for (const key of queueKeys()) items().delete(key);
    for (const [key, value] of stored) items().set(key, value);
    return open();
  };

  // Two captures of the 25th, as a start that recovered one can find: clearing the older one fails.
  jest.mocked(SecureStore.deleteItemAsync).mockRejectedValueOnce(new Error("The Keychain is not available."));
  const duplicate = start([[INDEX, JSON.stringify({ used: "111" })], [`${INDEX}.0`, kept("2026-09-25", 1)], [`${INDEX}.1`, kept("2026-09-25", 2)], [`${INDEX}.2`, kept("2026-09-27", 3)]]);
  await expect(duplicate.queue.ready).rejects.toThrow("The Keychain is not available.");
  const shown = duplicate.latest().entries;
  expect(shown.map((entry) => [entry.date, entry.queuedAt])).toEqual([["2026-09-25", 1]]);
  // The person's discard changes nothing, and a capture is refused, until the next start.
  await duplicate.queue.discard(shown[0]);
  await expect(duplicate.queue.add(capture("2026-09-28"))).rejects.toThrow("The Keychain is not available.");
  duplicate.queue.close();
  const next = open();
  await next.queue.ready;
  expect(next.latest().entries.map((entry) => [entry.date, entry.queuedAt])).toEqual([["2026-09-25", 2], ["2026-09-27", 3]]);
  next.queue.close();

  // A corrupt slot 1 is cleared, but writing the index without it fails.
  jest.mocked(SecureStore.setItemAsync).mockRejectedValueOnce(new Error("The Keychain is not available."));
  const untidy = start([[INDEX, JSON.stringify({ used: "111" })], [`${INDEX}.0`, kept("2026-09-25", 1)], [`${INDEX}.1`, "{"], [`${INDEX}.2`, kept("2026-09-27", 3)]]);
  await expect(untidy.queue.ready).rejects.toThrow("The Keychain is not available.");
  await untidy.queue.discard(untidy.latest().entries[0]);
  untidy.queue.close();
  const after = open();
  await after.queue.ready;
  expect(after.latest().entries.map((entry) => [entry.date, entry.queuedAt])).toEqual([["2026-09-25", 1], ["2026-09-27", 3]]);
  expect(JSON.parse(items().get(INDEX)!)).toEqual({ used: "101" });
});

it("refuses a capture from a queue that a newer one read the Keychain past before it was kept", async () => {
  const api = revenueApi();
  const first = open();
  await first.queue.add(capture("2026-09-25"));
  await settle(first.queue);

  // The app locks and unlocks while the second queue is still loading, with a capture waiting on that load.
  const second = open();
  const late = second.queue.add(capture("2026-09-27"));
  second.queue.close();
  const third = open();
  const outcome = await late.then(
    () => "kept",
    (error: Error) => error.message,
  );
  await third.queue.ready;
  await third.queue.add(capture("2026-09-28", { amount: 1800 }));
  await settle(third.queue);

  // A capture reported as kept would still be here; this one was refused, and nothing was written over.
  const last = open();
  await last.queue.ready;
  expect({ outcome, shown: summary(last.latest().entries) }).toEqual({
    outcome: "The app locked before this entry was kept. Capture it again.",
    shown: ["2026-09-25 1000 pending", "2026-09-28 1800 pending"],
  });
  api.answer(() => [200, { version: 1 }]);
  await last.queue.sync();
  expect(api.reached.map((sent) => sent.date)).toEqual(["2026-09-25", "2026-09-28"]);
});

it("still keeps a capture from a queue that closed while no newer queue had read the Keychain", async () => {
  const api = revenueApi();
  const first = open();
  await first.queue.ready;

  // Saved just as the app locks: nothing else has read the queue back yet, so keeping it overwrites nothing.
  const saving = first.queue.add(capture("2026-09-25"));
  first.queue.close();
  await expect(saving).resolves.toBeUndefined();

  const next = open();
  await next.queue.ready;
  expect(summary(next.latest().entries)).toEqual(["2026-09-25 1000 pending"]);
  api.answer(() => [200, { version: 1 }]);
  await next.queue.sync();
  expect(api.reached.map((sent) => sent.date)).toEqual(["2026-09-25"]);
});
