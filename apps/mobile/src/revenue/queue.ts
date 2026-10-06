import { addNetworkStateListener } from "expo-network";
import { useEffect, useMemo, useRef, useState } from "react";

import { REVENUE_NOTE_LIMIT, REVENUE_REASONS } from "@xcode/shared/revenue";

import { SessionEndedError, apiGet, apiPutResult } from "../lib/api";
import { read } from "../lib/storage";
import { vault } from "../lib/vault";
import { dayLabel, isDate, shiftDate } from "./dates";
import {
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
//
// The Keychain cannot list its keys, and the app can be killed between any two writes (each write on its own is all
// or nothing). So every slot holding a capture is named by the stored index, except at most one, which is the stored
// index's lowest free slot: a new capture takes the lowest free slot and is written there before the index names it;
// a slot is emptied before the index frees it; a queue counts a slot as used only once the stored index names it; and
// each change finishes its writes before the next starts. Opening reads that one slot as well, so a capture kept just
// before a kill is found, not written over. A kill after the API accepted a capture but before its slot was emptied
// sends it once more at the next start; the API answers an identical replay with 200 and changes nothing.

export const QUEUE_LIMIT = 500;
const MESSAGE_LIMIT = 160;
const MAX_ATTEMPTS = 10;
const STATES: QueueState[] = ["pending", "blocked", "conflict", "failed"];

export class QueueFullError extends Error {
  constructor() {
    super(
      `This phone is holding ${QUEUE_LIMIT} revenue entries that have not been sent. Connect to the internet so they can be sent, then save this one.`,
    );
  }
}

// Queues belong to the person (by mobile number) who captured them, and only their session sends them.
const indexKey = (owner: string) => `xcode.revenue-queue.${owner}`;
const slotKey = (owner: string, slot: number) => `${indexKey(owner)}.${slot}`;
const keyOf = (vehicleId: string, date: string) => `${vehicleId}/${date}`;

// Slots in use: "1" marks one; trailing free slots are trimmed.
function withSlot(bits: string, slot: number, inUse: boolean) {
  const padded = bits.padEnd(slot + 1, "0");
  return (
    padded.slice(0, slot) +
    (inUse ? "1" : "0") +
    padded.slice(slot + 1)
  ).replace(/0+$/, "");
}
// The lowest free slot, or -1 when the queue is full.
function firstFree(bits: string) {
  const free = bits.indexOf("0");
  if (free >= 0) return free;
  return bits.length < QUEUE_LIMIT ? bits.length : -1;
}

const text = (value: unknown, limit: number): value is string =>
  typeof value === "string" && value.length <= limit;
const orNull = (value: unknown, valid: (value: unknown) => boolean) =>
  value === null || valid(value);
const whole = (value: unknown) => Number.isInteger(value);

const validSaved = (value: unknown) => {
  const saved = value as SavedValue;
  return (
    typeof saved === "object" &&
    orNull(
      saved.amount,
      (amount) => typeof amount === "number" && Number.isFinite(amount),
    ) &&
    orNull(saved.reason, (reason) => text(reason, 20)) &&
    orNull(saved.note, (note) => text(note, REVENUE_NOTE_LIMIT)) &&
    orNull(saved.version, whole) &&
    (saved.canEdit === undefined || typeof saved.canEdit === "boolean")
  );
};

const validCapture = (entry: QueuedCapture) =>
  text(entry.vehicleId, 64) &&
  entry.vehicleId.length > 0 &&
  text(entry.registration, 40) &&
  isDate(entry.date) &&
  (entry.amount === null
    ? REVENUE_REASONS.includes(entry.reason!)
    : typeof entry.amount === "number" &&
      Number.isFinite(entry.amount) &&
      entry.amount > 0 &&
      entry.reason === null) &&
  orNull(entry.note, (note) => text(note, REVENUE_NOTE_LIMIT)) &&
  orNull(entry.version, whole) &&
  STATES.includes(entry.state) &&
  text(entry.message, MESSAGE_LIMIT) &&
  orNull(entry.earliestMissing, isDate) &&
  orNull(entry.current, validSaved) &&
  Number.isFinite(entry.queuedAt) &&
  (entry.attempts === undefined || whole(entry.attempts)) &&
  (entry.lastAttemptAt === undefined || Number.isFinite(entry.lastAttemptAt));

const savedValue = (cell: RevenueCell): SavedValue => ({
  amount: cell.amount,
  reason: cell.reason,
  note: cell.note,
  version: cell.version ?? null,
  canEdit: cell.canEdit,
});

// Oldest day first, so an earlier day for a vehicle always reaches the API before a later one.
const byDay = (a: QueuedCapture, b: QueuedCapture) =>
  a.date.localeCompare(b.date) || a.registration.localeCompare(b.registration);

// Storage work for one person runs a step at a time, across every queue opened for them: a queue closing after
// a lock can never write over the one the next unlock opens.
const locks = new Map<string, Promise<unknown>>();
function exclusive<T>(owner: string, work: () => Promise<T>): Promise<T> {
  const next = (locks.get(owner) ?? Promise.resolve()).then(work);
  locks.set(
    owner,
    next.catch(() => undefined),
  );
  return next;
}
// The queue that last read each person's slots back. Only it knows every slot in use, so only it may take a new one.
const readBy = new Map<string, object>();

export type NewCapture = Pick<
  QueuedCapture,
  | "vehicleId"
  | "registration"
  | "date"
  | "amount"
  | "reason"
  | "note"
  | "version"
>;
export type QueueSnapshot = {
  entries: QueuedCapture[];
  revision: number;
  loaded: boolean;
  syncing: boolean;
};

export function openQueue(
  owner: string,
  hooks: {
    onChange: (snapshot: QueueSnapshot) => void;
    onSessionEnded: () => void;
  },
) {
  const held = new Map<string, { slot: number; entry: QueuedCapture }>();
  // Never ahead of the stored index: a slot is marked here only after an index naming it was written.
  let used = "";
  // Set when the load has finished. A queue whose load failed writes nothing, since it may not know every slot.
  let intact = false;
  let loaded = false;
  let closed = false;
  let syncing = false;
  let running: Promise<void> | null = null;
  let again = false;
  // Counts answers that changed what the API holds (a save, or a conflict with someone else's), so screens reload.
  let revision = 0;

  const entries = () =>
    [...held.values()].map((item) => item.entry).sort(byDay);
  const find = (entry: QueuedCapture) =>
    held.get(keyOf(entry.vehicleId, entry.date))?.entry;
  const changed = () => {
    if (!closed)
      hooks.onChange({ entries: entries(), revision, loaded, syncing });
  };
  const saveIndex = (bits: string) =>
    vault.set(indexKey(owner), JSON.stringify({ used: bits }));

  // One index read, then one read per waiting capture and one for the index's lowest free slot, where a capture
  // kept just before a kill would be. A slot that is missing or fails its check is cleared, as storage.ts treats
  // corrupt state.
  const self = {};
  const ready = exclusive(owner, async () => {
    readBy.set(owner, self);
    const index = await read<{ used: string }>(
      indexKey(owner),
      (value) =>
        typeof value.used === "string" &&
        value.used.length <= QUEUE_LIMIT &&
        /^[01]*$/.test(value.used),
    );
    const stored = (index?.used ?? "").replace(/0+$/, "");
    const unnamed = firstFree(stored);
    const slots = [...stored]
      .flatMap((bit, slot) => (bit === "1" ? [slot] : []))
      .concat(unnamed >= 0 ? [unnamed] : []);
    const found = await Promise.all(
      slots.map((slot) =>
        read<QueuedCapture>(slotKey(owner, slot), validCapture),
      ),
    );
    for (const [position, stored] of found.entries()) {
      if (!stored) continue;
      const entry: QueuedCapture = {
        ...stored,
        attempts: stored.attempts ?? 0,
        lastAttemptAt: stored.lastAttemptAt ?? 0,
      };
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
    const next = [...held.values()].reduce(
      (bits, { slot }) => withSlot(bits, slot, true),
      "",
    );
    if (next !== stored) await saveIndex(next);
    used = next;
    intact = true;
  }).finally(() => {
    loaded = true;
    changed();
  });

  // Replaces the stored entry for a vehicle and day in one write, unless the queue closed or a newer capture
  // replaced it meanwhile.
  function update(
    sent: QueuedCapture,
    change: Partial<QueuedCapture> | "remove",
  ) {
    return exclusive(owner, async () => {
      const key = keyOf(sent.vehicleId, sent.date);
      const now = held.get(key);
      if (closed || !intact || !now || now.entry !== sent) return;
      if (change === "remove") {
        // The capture goes before its bit; the bit goes here even if the index write fails, as the slot is empty.
        await vault.remove(slotKey(owner, now.slot));
        held.delete(key);
        used = withSlot(used, now.slot, false);
        await saveIndex(used);
        return;
      }
      const entry = {
        ...sent,
        ...change,
        message: (change.message ?? sent.message).slice(0, MESSAGE_LIMIT),
      };
      await vault.set(slotKey(owner, now.slot), JSON.stringify(entry));
      held.set(key, { slot: now.slot, entry });
    }).then(changed);
  }

  // A 409 without the saved record (two captures raced to create it): read what the API holds for that day now.
  async function savedNow(entry: QueuedCapture): Promise<SavedValue | null> {
    try {
      const week = await apiGet<RevenueWeek>(
        `setup/revenue?weekStart=${shiftDate(entry.date, -6)}&vehicleId=${encodeURIComponent(entry.vehicleId)}`,
      );
      const cell = week.vehicles
        .find((vehicle) => vehicle.id === entry.vehicleId)
        ?.days.find((day) => day.date === entry.date);
      return cell && cell.status !== "missing" ? savedValue(cell) : null;
    } catch {
      return null;
    }
  }

  // An answer that says to try again later counts as an attempt; offline tries do not.
  const tried = (entry: QueuedCapture) => ({
    attempts: entry.attempts + 1,
    lastAttemptAt: Date.now(),
  });

  // Sends one capture. false stops the round: no connection, no session, or the API is struggling. The entry stays.
  async function send(entry: QueuedCapture) {
    const body: SaveRevenue = {
      amount: entry.amount,
      reason: entry.reason,
      note: entry.note,
      version: entry.version,
    };
    let result: { status: number; body: RevenueProblem };
    try {
      result = await apiPutResult<RevenueProblem>(
        `setup/revenue/${encodeURIComponent(entry.vehicleId)}/${entry.date}`,
        body,
      );
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
      const current = problem.current
        ? savedValue(problem.current)
        : await savedNow(entry);
      revision += 1;
      await update(entry, {
        state: "conflict",
        message: "Someone else saved this day first.",
        current,
        earliestMissing: null,
      });
    } else if (status === 400 && isDate(problem.earliestMissing)) {
      await update(entry, {
        state: "blocked",
        message: `Capture ${dayLabel(problem.earliestMissing)} first.`,
        earliestMissing: problem.earliestMissing,
      });
    } else if (status === 400 || status === 403 || status === 404) {
      const fallback =
        status === 404
          ? "This vehicle is no longer in your view."
          : status === 403
            ? "Your access does not allow this entry."
            : "The API did not accept this entry.";
      await update(entry, {
        state: "failed",
        message: why || fallback,
        earliestMissing: null,
      });
    } else if (status === 429) {
      await update(entry, tried(entry));
      return false;
    } else if (status >= 400 && status < 500) {
      await update(entry, {
        state: "failed",
        message: why || "The API did not accept this entry.",
        earliestMissing: null,
      });
    } else {
      if (entry.attempts + 1 < MAX_ATTEMPTS) {
        await update(entry, tried(entry));
        return false;
      }
      await update(entry, {
        ...tried(entry),
        state: "failed",
        message: "This entry could not be sent after several tries.",
        earliestMissing: null,
      });
    }
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
          for (const entry of entries().filter(
            (item) => item.state === "pending" || item.state === "blocked",
          )) {
            // Discarded or replaced since the pass began: the replacement goes in the next pass.
            if (find(entry) !== entry) continue;
            if (
              entry.attempts > 0 &&
              Date.now() - entry.lastAttemptAt <
                Math.min(30_000, 1000 * 2 ** Math.min(entry.attempts - 1, 4))
            )
              continue;
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
      // A newer queue for this person read the slots back while this one waited: it would not know the slot taken
      // here, and would write over it. A queue that merely closed (the app locked) still keeps what was saved.
      if (readBy.get(owner) !== self)
        throw new Error(
          "The app locked before this entry was kept. Capture it again.",
        );
      const key = keyOf(capture.vehicleId, capture.date);
      const existing = held.get(key);
      const entry: QueuedCapture = {
        ...capture,
        registration: capture.registration.slice(0, 40),
        state: "pending",
        message: "",
        earliestMissing: null,
        current: null,
        queuedAt: Date.now(),
        attempts: 0,
        lastAttemptAt: 0,
      };
      if (existing) {
        await vault.set(slotKey(owner, existing.slot), JSON.stringify(entry));
        held.set(key, { slot: existing.slot, entry });
        return;
      }
      const slot = firstFree(used);
      if (slot < 0) throw new QueueFullError();
      const next = withSlot(used, slot, true);
      try {
        await vault.set(slotKey(owner, slot), JSON.stringify(entry));
        await saveIndex(next);
      } catch (error) {
        // Not kept: the slot stays free here, and is cleared if the Keychain allows. It held nothing kept before.
        await vault.remove(slotKey(owner, slot)).catch(() => undefined);
        throw error;
      }
      used = next;
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
      await update(now, {
        state: "pending",
        message: "",
        version: now.current?.version ?? now.version,
        current: null,
        attempts: 0,
        lastAttemptAt: 0,
      });
      await sync();
    },
    retry: async (entry: QueuedCapture) => {
      const now = find(entry);
      if (!now) return;
      await update(now, {
        state: "pending",
        message: "",
        attempts: 0,
        lastAttemptAt: 0,
      });
      await sync();
    },
    close: () => {
      closed = true;
    },
  };
}

export type RevenueQueue = Omit<
  ReturnType<typeof openQueue>,
  "ready" | "close"
> &
  QueueSnapshot;

// The signed-in person's queue, kept under their account id (a phone number can change or be given to someone else).
// A person saved by a Phase 1 app has no id until they next sign in online, so they get no queue and capturing says
// so, rather than a queue under a key that could strand or expose what is in it. It sends what is waiting when the shell opens (every unlock, since leaving the
// app locks it), after each capture, and when the network comes back.
export function useRevenueQueue(
  owner: string | undefined,
  onSessionEnded: () => void,
): RevenueQueue {
  const [snapshot, setSnapshot] = useState<QueueSnapshot>({
    entries: [],
    revision: 0,
    loaded: false,
    syncing: false,
  });
  const queue = useRef<ReturnType<typeof openQueue> | null>(null);
  const ended = useRef(onSessionEnded);
  useEffect(() => {
    ended.current = onSessionEnded;
  });

  useEffect(() => {
    if (!owner) {
      setSnapshot({ entries: [], revision: 0, loaded: true, syncing: false });
      return;
    }
    const opened = openQueue(owner, {
      onChange: setSnapshot,
      onSessionEnded: () => ended.current(),
    });
    queue.current = opened;
    void opened.sync();
    const network = addNetworkStateListener((state) => {
      if (state.isConnected && state.isInternetReachable !== false)
        void opened.sync();
    });
    return () => {
      network.remove();
      opened.close();
      queue.current = null;
    };
  }, [owner]);

  return useMemo(() => {
    const open = () => {
      if (!owner)
        throw new Error(
          "Connect to the internet and unlock the app once to turn on revenue capture on this phone.",
        );
      if (!queue.current)
        throw new Error("Revenue capture is still starting. Try again.");
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
  }, [snapshot, owner]);
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
