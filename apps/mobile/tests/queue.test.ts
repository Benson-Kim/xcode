import { saveSession } from "../src/lib/storage";
import { QUEUE_LIMIT, QueueFullError, openQueue, type NewCapture, type QueueSnapshot } from "../src/revenue/queue";
import { fakeApi } from "./fakeApi";

const OWNER = "0712345678";
const items = () => require("expo-secure-store").__items as Map<string, string>;
const queueKeys = () => [...items().keys()].filter((key) => key.startsWith(`xcode.revenue-queue.${OWNER}`));
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
