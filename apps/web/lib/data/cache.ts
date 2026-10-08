export type Snapshot<T> = {
  value: T | undefined;
  error: string;
  validating: boolean;
};
export type Loaded<T> = { value: T; error?: string };
export type Loader<T> = (
  signal: AbortSignal,
  publish: (value: T) => void,
  previous: T | undefined,
) => Promise<Loaded<T>>;

type Run = { controller: AbortController };

type Entry = {
  key: string;
  path: string;
  load: Loader<unknown>;
  snapshot: Snapshot<unknown>;
  stale: boolean;
  fetchedAt: number;
  subscribers: number;
  listeners: Set<() => void>;
  run: Run | null;
  controller: AbortController | null;
};

// A result this young is shown without asking the server again, so screens that open one after another share it.
const FRESH_MS = 2000;
const MAX_IDLE_ENTRIES = 200;

const EMPTY: Snapshot<never> = {
  value: undefined,
  error: "",
  validating: false,
};
const entries = new Map<string, Entry>();

function update(entry: Entry, patch: Partial<Snapshot<unknown>>) {
  entry.snapshot = { ...entry.snapshot, ...patch };
  for (const listener of [...entry.listeners]) listener();
}

function start(entry: Entry) {
  entry.run?.controller.abort();
  const run: Run = { controller: new AbortController() };
  entry.run = run;
  entry.controller = run.controller;
  const current = () => entries.get(entry.key) === entry && entry.run === run;
  update(entry, { validating: true });
  entry
    .load(
      run.controller.signal,
      (value) => {
        if (current()) update(entry, { value });
      },
      entry.snapshot.value,
    )
    .then(
      ({ value, error = "" }) => {
        if (!current()) return;
        entry.run = null;
        entry.stale = error !== "";
        if (!error) entry.fetchedAt = Date.now();
        update(entry, { value, error, validating: false });
      },
      (error: Error) => {
        if (!current()) return;
        entry.run = null;
        entry.stale = true;
        update(entry, { error: error.message, validating: false });
      },
    );
}

function needsFetch(entry: Entry) {
  return (
    entry.snapshot.value === undefined ||
    entry.snapshot.error !== "" ||
    entry.stale ||
    Date.now() - entry.fetchedAt >= FRESH_MS
  );
}

function evictIdle() {
  for (const [key, entry] of entries) {
    if (entries.size <= MAX_IDLE_ENTRIES) return;
    if (entry.subscribers === 0 && !entry.run) entries.delete(key);
  }
}

export function readSnapshot<T>(key: string | null): Snapshot<T> {
  return ((key !== null && entries.get(key)?.snapshot) || EMPTY) as Snapshot<T>;
}

// Shows whatever is cached for `key` at once and fetches only when nothing is in flight and the result is missing,
// stale or old. Everyone subscribed to a key shares one fetch; it is aborted when the last of them leaves.
export function subscribeEntry<T>(
  key: string,
  path: string,
  load: Loader<T>,
  listener: () => void,
) {
  let entry = entries.get(key);
  if (!entry) {
    entry = {
      key,
      path,
      load: load as Loader<unknown>,
      snapshot: EMPTY,
      stale: false,
      fetchedAt: 0,
      subscribers: 0,
      listeners: new Set(),
      run: null,
      controller: null,
    };
    entries.set(key, entry);
  }
  const joined = entry;
  joined.subscribers++;
  joined.listeners.add(listener);
  if (!joined.run && needsFetch(joined)) start(joined);
  let subscribed = true;
  return () => {
    if (!subscribed) return;
    subscribed = false;
    joined.listeners.delete(listener);
    if (--joined.subscribers > 0) return;
    joined.controller?.abort();
    if (joined.run) {
      joined.run = null;
      joined.snapshot = { ...joined.snapshot, validating: false };
    }
    if (entries.get(key) !== joined) return;
    if (joined.snapshot.value === undefined) entries.delete(key);
    else evictIdle();
  };
}

// A forced refetch, joining one that is already in flight.
export function reloadEntry(key: string | null) {
  const entry = key === null ? undefined : entries.get(key);
  if (entry && entry.subscribers > 0 && !entry.run) start(entry);
}

// Called after a successful change. What nobody is showing is dropped; what is on screen is marked stale and
// refetched at once when a fetch was already under way, since that fetch may have read the data before the change.
export function invalidateDataCache(prefix = "setup/") {
  for (const entry of [...entries.values()]) {
    if (!entry.path.startsWith(prefix)) continue;
    if (entry.subscribers === 0) {
      entry.run?.controller.abort();
      entries.delete(entry.key);
      continue;
    }
    entry.stale = true;
    if (entry.run) start(entry);
  }
}

// Cached data is specific to whoever is signed in: drop all of it when the session ends or the user changes.
export function clearDataCache() {
  const dropped = [...entries.values()];
  entries.clear();
  for (const entry of dropped) {
    entry.run?.controller.abort();
    entry.run = null;
    for (const listener of [...entry.listeners]) listener();
  }
}
