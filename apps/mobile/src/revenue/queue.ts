import { useEffect, useMemo, useRef, useState } from "react";
import { addNetworkStateListener } from "expo-network";
import { SessionEndedError, apiGet, apiPutResult } from "../lib/api";
import { read } from "../lib/storage";
import { vault } from "../lib/vault";
import { dayLabel, isDate, shiftDate } from "./dates";
import {
  NOTE_LIMIT,
  REASONS,
  type QueueState,
  type QueuedCapture,
  type RevenueCell,
  type RevenueProblem,
  type RevenueWeek,
  type SaveRevenue,
  type SavedValue,
} from "./types";

// "The phone captures offline and syncs when a connection returns. No entry is ever lost."
// Every capture is written to the Keychain before anything is sent, and leaves it only when the API accepts it
// (200) or the person discards it. Each capture has its own small entry in a numbered slot; the index holds one
// character per slot, so it stays under QUEUE_LIMIT bytes however many vehicles and days are waiting.

export const QUEUE_LIMIT = 500;
const MESSAGE_LIMIT = 160;
const STATES: QueueState[] = ["pending", "blocked", "conflict", "failed"];

export class QueueFullError extends Error {
  constructor() {
    super(`This phone is holding ${QUEUE_LIMIT} revenue entries that have not been sent. Connect to the internet so they can be sent, then save this one.`);
  }
}

// Queues belong to the person (by mobile number) who captured them, and only their session sends them.
const indexKey = (owner: string) => `xcode.revenue-queue.${owner}`;
const slotKey = (owner: string, slot: number) => `${indexKey(owner)}.${slot}`;
const keyOf = (vehicleId: string, date: string) => `${vehicleId}/${date}`;

const text = (value: unknown, limit: number): value is string => typeof value === "string" && value.length <= limit;
const orNull = (value: unknown, valid: (value: unknown) => boolean) => value === null || valid(value);
const whole = (value: unknown) => Number.isInteger(value);

const validSaved = (value: unknown) => {
  const saved = value as SavedValue;
  return (
    typeof saved === "object" &&
    orNull(saved.amount, (amount) => typeof amount === "number" && Number.isFinite(amount)) &&
    orNull(saved.reason, (reason) => text(reason, 20)) &&
    orNull(saved.note, (note) => text(note, NOTE_LIMIT)) &&
    orNull(saved.version, whole)
  );
};

const validCapture = (entry: QueuedCapture) =>
  text(entry.vehicleId, 64) &&
  entry.vehicleId.length > 0 &&
  text(entry.registration, 40) &&
  isDate(entry.date) &&
  (entry.amount === null
    ? REASONS.includes(entry.reason!)
    : typeof entry.amount === "number" && Number.isFinite(entry.amount) && entry.amount > 0 && entry.reason === null) &&
  orNull(entry.note, (note) => text(note, NOTE_LIMIT)) &&
  orNull(entry.version, whole) &&
  STATES.includes(entry.state) &&
  text(entry.message, MESSAGE_LIMIT) &&
  orNull(entry.earliestMissing, isDate) &&
  orNull(entry.current, validSaved) &&
  Number.isFinite(entry.queuedAt);

const savedValue = (cell: RevenueCell): SavedValue => ({ amount: cell.amount, reason: cell.reason, note: cell.note, version: cell.version ?? null });

// Oldest day first, so an earlier day for a vehicle always reaches the API before a later one.
const byDay = (a: QueuedCapture, b: QueuedCapture) => a.date.localeCompare(b.date) || a.registration.localeCompare(b.registration);

// Storage work for one person runs a step at a time, across every queue opened for them: a queue closing after
// a lock can never write over the one the next unlock opens.
const locks = new Map<string, Promise<unknown>>();
function exclusive<T>(owner: string, work: () => Promise<T>): Promise<T> {
  const next = (locks.get(owner) ?? Promise.resolve()).then(work);
  locks.set(owner, next.catch(() => undefined));
  return next;
}

export type NewCapture = Pick<QueuedCapture, "vehicleId" | "registration" | "date" | "amount" | "reason" | "note" | "version">;
export type QueueSnapshot = { entries: QueuedCapture[]; revision: number; loaded: boolean; syncing: boolean };

export function openQueue(owner: string, hooks: { onChange: (snapshot: QueueSnapshot) => void; onSessionEnded: () => void }) {
  const held = new Map<string, { slot: number; entry: QueuedCapture }>();
  // "1" marks a slot in use; trailing free slots are trimmed.
  let used = "";
  let loaded = false;
  let closed = false;
  let syncing = false;
  let running: Promise<void> | null = null;
  let again = false;
  // Counts answers that changed what the API holds (a save, or a conflict with someone else's), so screens reload.
  let revision = 0;

  const entries = () => [...held.values()].map((item) => item.entry).sort(byDay);
  const find = (entry: QueuedCapture) => held.get(keyOf(entry.vehicleId, entry.date))?.entry;
  const changed = () => {
    if (!closed) hooks.onChange({ entries: entries(), revision, loaded, syncing });
  };
  const saveIndex = () => vault.set(indexKey(owner), JSON.stringify({ used }));
  function mark(slot: number, inUse: boolean) {
    const bits = used.padEnd(slot + 1, "0");
    used = (bits.slice(0, slot) + (inUse ? "1" : "0") + bits.slice(slot + 1)).replace(/0+$/, "");
  }
  function firstFree() {
    const free = used.indexOf("0");
    if (free >= 0) return free;
    return used.length < QUEUE_LIMIT ? used.length : -1;
  }

  // One index read, then one read per waiting capture. A slot that is missing or fails its check is cleared,
  // as storage.ts treats corrupt state.
  const ready = exclusive(owner, async () => {
    const index = await read<{ used: string }>(
      indexKey(owner),
      (value) => typeof value.used === "string" && value.used.length <= QUEUE_LIMIT && /^[01]*$/.test(value.used),
    );
    const stored = index?.used ?? "";
    const slots = [...stored].flatMap((bit, slot) => (bit === "1" ? [slot] : []));
    const found = await Promise.all(slots.map((slot) => read<QueuedCapture>(slotKey(owner, slot), validCapture)));
    for (const [position, entry] of found.entries()) {
      if (!entry) continue;
      const slot = slots[position];
      const key = keyOf(entry.vehicleId, entry.date);
      const other = held.get(key);
      if (other && other.entry.queuedAt >= entry.queuedAt) {
        await vault.remove(slotKey(owner, slot));
        continue;
      }
      if (other) await vault.remove(slotKey(owner, other.slot));
      held.set(key, { slot, entry });
    }
    for (const { slot } of held.values()) mark(slot, true);
    if (used !== stored.replace(/0+$/, "")) await saveIndex();
  }).finally(() => {
    loaded = true;
    changed();
  });

  // Replaces the stored entry for a vehicle and day, unless the queue closed or a newer capture replaced it meanwhile.
  function update(sent: QueuedCapture, change: Partial<QueuedCapture> | "remove") {
    return exclusive(owner, async () => {
      const key = keyOf(sent.vehicleId, sent.date);
      const now = held.get(key);
      if (closed || !now || now.entry !== sent) return;
      if (change === "remove") {
        await vault.remove(slotKey(owner, now.slot));
        held.delete(key);
        mark(now.slot, false);
        await saveIndex();
        return;
      }
      const entry = { ...sent, ...change, message: (change.message ?? sent.message).slice(0, MESSAGE_LIMIT) };
      await vault.set(slotKey(owner, now.slot), JSON.stringify(entry));
      held.set(key, { slot: now.slot, entry });
    }).then(changed);
  }

  // A 409 without the saved record (two captures raced to create it): read what the API holds for that day now.
  async function savedNow(entry: QueuedCapture): Promise<SavedValue | null> {
    try {
      const week = await apiGet<RevenueWeek>(`setup/revenue?weekStart=${shiftDate(entry.date, -6)}&vehicleId=${encodeURIComponent(entry.vehicleId)}`);
      const cell = week.vehicles.find((vehicle) => vehicle.id === entry.vehicleId)?.days.find((day) => day.date === entry.date);
      return cell && cell.status !== "missing" ? savedValue(cell) : null;
    } catch {
      return null;
    }
  }

  // Sends one capture. false stops the round: no connection, no session, or the API is struggling. The entry stays.
  async function send(entry: QueuedCapture) {
    const body: SaveRevenue = { amount: entry.amount, reason: entry.reason, note: entry.note, version: entry.version };
    let result: { status: number; body: RevenueProblem };
    try {
      result = await apiPutResult<RevenueProblem>(`setup/revenue/${encodeURIComponent(entry.vehicleId)}/${entry.date}`, body);
    } catch (error) {
      if (error instanceof SessionEndedError && !closed) hooks.onSessionEnded();
      return false;
    }
    const { status, body: problem } = result;
    const why = problem.detail || problem.title || "";
    if (status >= 200 && status < 300) {
      revision += 1;
      await update(entry, "remove");
    } else if (status === 409) {
      const current = problem.current ? savedValue(problem.current) : await savedNow(entry);
      revision += 1;
      await update(entry, { state: "conflict", message: "Someone else saved this day first.", current, earliestMissing: null });
    } else if (status === 400 && isDate(problem.earliestMissing)) {
      await update(entry, { state: "blocked", message: `Capture ${dayLabel(problem.earliestMissing)} first.`, earliestMissing: problem.earliestMissing });
    } else if (status === 400 || status === 403 || status === 404) {
      const fallback = status === 404 ? "This vehicle is no longer in your view." : status === 403 ? "Your access does not allow this entry." : "The API did not accept this entry.";
      await update(entry, { state: "failed", message: why || fallback, earliestMissing: null });
    } else return false;
    return true;
  }

  // Sends what is waiting, oldest day first. One round at a time: a call during a round asks for another pass
  // and waits for the same round.
  function sync(): Promise<void> {
    if (running) {
      again = true;
      return running;
    }
    syncing = true;
    changed();
    running = (async () => {
      try {
        await ready;
        do {
          again = false;
          for (const entry of entries().filter((item) => item.state === "pending" || item.state === "blocked")) {
            // Discarded or replaced since the pass began: the replacement goes in the next pass.
            if (find(entry) !== entry) continue;
            if (closed || !(await send(entry))) return;
          }
        } while (again && !closed);
      } catch {
        // The Keychain could not be read or written: what is stored stays for the next try.
      }
    })().finally(() => {
      running = null;
      syncing = false;
      changed();
    });
    return running;
  }

  // Kept on the phone before anything is sent. A new capture of the same vehicle and day replaces the waiting one.
  async function add(capture: NewCapture) {
    await ready;
    await exclusive(owner, async () => {
      const key = keyOf(capture.vehicleId, capture.date);
      const existing = held.get(key);
      const slot = existing?.slot ?? firstFree();
      if (slot < 0) throw new QueueFullError();
      const entry: QueuedCapture = {
        ...capture,
        registration: capture.registration.slice(0, 40),
        state: "pending",
        message: "",
        earliestMissing: null,
        current: null,
        queuedAt: Date.now(),
      };
      await vault.set(slotKey(owner, slot), JSON.stringify(entry));
      if (!existing) {
        mark(slot, true);
        await saveIndex();
      }
      held.set(key, { slot, entry });
    });
    changed();
    void sync();
  }

  return {
    ready,
    add,
    sync,
    // "Keep saved value", or discarding a refused capture: the person's own choice.
    discard: async (entry: QueuedCapture) => {
      const now = find(entry);
      if (now) await update(now, "remove");
    },
    // "Replace with mine": send again over the version the API holds.
    replace: async (entry: QueuedCapture) => {
      const now = find(entry);
      if (!now) return;
      await update(now, { state: "pending", message: "", version: now.current?.version ?? now.version, current: null });
      await sync();
    },
    retry: async (entry: QueuedCapture) => {
      const now = find(entry);
      if (!now) return;
      await update(now, { state: "pending", message: "" });
      await sync();
    },
    close: () => {
      closed = true;
    },
  };
}

export type RevenueQueue = Omit<ReturnType<typeof openQueue>, "ready" | "close"> & QueueSnapshot;

// The signed-in person's queue. It sends what is waiting when the shell opens (every unlock, since leaving the
// app locks it), after each capture, and when the network comes back.
export function useRevenueQueue(owner: string, onSessionEnded: () => void): RevenueQueue {
  const [snapshot, setSnapshot] = useState<QueueSnapshot>({ entries: [], revision: 0, loaded: false, syncing: false });
  const queue = useRef<ReturnType<typeof openQueue> | null>(null);
  const ended = useRef(onSessionEnded);
  useEffect(() => {
    ended.current = onSessionEnded;
  });

  useEffect(() => {
    const opened = openQueue(owner, { onChange: setSnapshot, onSessionEnded: () => ended.current() });
    queue.current = opened;
    void opened.sync();
    const network = addNetworkStateListener((state) => {
      if (state.isConnected && state.isInternetReachable !== false) void opened.sync();
    });
    return () => {
      network.remove();
      opened.close();
      queue.current = null;
    };
  }, [owner]);

  return useMemo(() => {
    const open = () => {
      if (!queue.current) throw new Error("Revenue capture is still starting. Try again.");
      return queue.current;
    };
    return {
      ...snapshot,
      add: async (capture: NewCapture) => open().add(capture),
      sync: async () => queue.current?.sync(),
      discard: async (entry: QueuedCapture) => open().discard(entry),
      replace: async (entry: QueuedCapture) => open().replace(entry),
      retry: async (entry: QueuedCapture) => open().retry(entry),
    };
  }, [snapshot]);
}

// Counts for the Revenue tab: waiting (pending, or waiting for an earlier day), conflicts and refusals.
export function queueCounts(entries: QueuedCapture[]) {
  const counts = { waiting: 0, conflicts: 0, failed: 0 };
  for (const entry of entries) {
    if (entry.state === "conflict") counts.conflicts += 1;
    else if (entry.state === "failed") counts.failed += 1;
    else counts.waiting += 1;
  }
  return counts;
}
