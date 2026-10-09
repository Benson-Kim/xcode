import * as Crypto from "expo-crypto";

import type { PersonIdentity } from "@xcode/shared/auth";
import type { SessionTokens } from "@xcode/shared/auth";

import { pbkdf2Sha256 } from "./pbkdf2";
import { vault } from "./vault";

const keys = {
  device: "xcode.device",
  session: "xcode.session",
  person: "xcode.person",
  pinCheck: "xcode.pin-check",
  offlineTries: "xcode.offline-tries",
  captureList: "xcode.capture-list",
};

export interface StoredSession extends SessionTokens {
  phoneNumber: string;
  lastOnlineAt?: number;
}

// A trusted phone unlocks without internet only within 72 hours of its last online sign-in or renewal.
export const OFFLINE_UNLOCK_HOURS = 72;
const OFFLINE_UNLOCK_MS = OFFLINE_UNLOCK_HOURS * 60 * 60 * 1000;

// The organization's wrong-PIN policy
export interface PinPolicy {
  lockoutThreshold: number;
  lockoutMinutes: number;
}

// What a phone uses until it has loaded the organization's policy
export const DEFAULT_PIN_POLICY: PinPolicy = {
  lockoutThreshold: 5,
  lockoutMinutes: 15,
};

// The bounds the for PIN
export const validPinPolicy = (policy: Partial<PinPolicy>) =>
  Number.isInteger(policy.lockoutThreshold) &&
  policy.lockoutThreshold! >= 3 &&
  policy.lockoutThreshold! <= 10 &&
  Number.isInteger(policy.lockoutMinutes) &&
  policy.lockoutMinutes! >= 1 &&
  policy.lockoutMinutes! <= 60;

export interface StoredPerson extends PersonIdentity, PinPolicy {
  userId?: string;
  phoneNumber: string;
  pinLength: number;
}

export interface OfflineTries {
  count: number;
  pausedUntil: number;
}

let devicePromise: Promise<string> | undefined;

export function getDeviceId(): Promise<string> {
  if (!devicePromise)
    devicePromise = (async () => {
      const existing = await vault.get(keys.device);
      if (existing) return existing;
      const id = Crypto.randomUUID();
      await vault.set(keys.device, id);
      return id;
    })().catch((error) => {
      devicePromise = undefined;
      throw error;
    });
  return devicePromise;
}

// Reads a stored JSON value, removing it when it is corrupt or fails the check rather than trusting it.
export async function read<T>(
  key: string,
  valid: (value: T) => boolean,
): Promise<T | null> {
  const value = await vault.get(key);
  if (!value) return null;
  try {
    const parsed = JSON.parse(value) as T;
    if (parsed && valid(parsed)) return parsed;
  } catch {
    /*  Clear corrupted state rather than trust it. */
  }
  await vault.remove(key);
  return null;
}

const write = (key: string, value: unknown) =>
  vault.set(key, JSON.stringify(value));

export async function saveSession(session: StoredSession): Promise<void> {
  await write(keys.session, session);
}

export function loadSession() {
  return read<StoredSession>(
    keys.session,
    (session) =>
      typeof session.phoneNumber === "string" &&
      session.phoneNumber.length > 0 &&
      typeof session.accessToken === "string" &&
      session.accessToken.length > 0 &&
      typeof session.refreshToken === "string" &&
      session.refreshToken.length > 0 &&
      (session.lastOnlineAt === undefined ||
        (Number.isFinite(session.lastOnlineAt) && session.lastOnlineAt! >= 0)),
  );
}

// When offline unlock stops working, or null when this phone is trusted for nobody.
export async function offlineUnlockUntil(): Promise<number | null> {
  const session = await loadSession();
  if (!session) return null;
  if (session.lastOnlineAt !== undefined)
    return session.lastOnlineAt + OFFLINE_UNLOCK_MS;
  const now = Date.now();
  await saveSession({ ...session, lastOnlineAt: now });
  return now + OFFLINE_UNLOCK_MS;
}

export async function clearSession(): Promise<void> {
  await vault.remove(keys.session);
}

export async function savePerson(person: StoredPerson): Promise<void> {
  await write(keys.person, person);
}

export async function loadPerson(): Promise<StoredPerson | null> {
  const person = await read<StoredPerson>(
    keys.person,
    (person) =>
      typeof person.phoneNumber === "string" &&
      person.phoneNumber.length > 0 &&
      (person.userId === undefined ||
        (typeof person.userId === "string" && person.userId.length > 0)) &&
      typeof person.firstName === "string" &&
      person.firstName.length > 0 &&
      typeof person.lastName === "string" &&
      person.lastName.length > 0 &&
      typeof person.role === "string" &&
      person.role.length > 0 &&
      Array.isArray(person.permissions) &&
      person.permissions.every(
        (permission) => typeof permission === "string",
      ) &&
      Number.isInteger(person.pinLength) &&
      person.pinLength >= 4 &&
      person.pinLength <= 8 &&
      // Absent on records saved before the policy was kept; those read as the defaults.
      ((person.lockoutThreshold === undefined &&
        person.lockoutMinutes === undefined) ||
        validPinPolicy(person)),
  );
  return person && { ...DEFAULT_PIN_POLICY, ...person };
}

// Keeps the organization's policy
export async function savePinPolicy(policy: PinPolicy): Promise<void> {
  const person = await loadPerson();
  if (person && validPinPolicy(policy))
    await savePerson({
      ...person,
      lockoutThreshold: policy.lockoutThreshold,
      lockoutMinutes: policy.lockoutMinutes,
    });
}

const PIN_CHECK_VERSION = 2;
const PBKDF2_ITERATIONS = 100_000;

function hexBytes(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function fromHex(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2)
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  return bytes;
}

async function pbkdf2(
  pin: string,
  saltHex: string,
  signal?: AbortSignal,
): Promise<string> {
  return hexBytes(
    await pbkdf2Sha256(
      new TextEncoder().encode(pin),
      fromHex(saltHex),
      PBKDF2_ITERATIONS,
      undefined,
      signal,
    ),
  );
}

async function digestV1(salt: string, pin: string) {
  return Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    `${salt}:${pin}`,
  );
}

interface PinCheck {
  version?: number;
  salt: string;
  hash: string;
  // Who signed in with the PIN, and at which security version. Absent on checks saved before it was kept.
  stamp?: string;
}

const BASE64URL =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

// The user an access token was issued to and their security version, which the server raises on every PIN change.
function tokenStamp(accessToken: string): string | undefined {
  let text = "";
  let bits = 0;
  let value = 0;
  for (const char of accessToken.split(".")[1] ?? "") {
    const digit = BASE64URL.indexOf(char);
    if (digit < 0) return undefined;
    value = ((value << 6) | digit) & 0xffff;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      text += String.fromCharCode((value >> bits) & 0xff);
    }
  }
  try {
    const { sub, version } = JSON.parse(text) as {
      sub?: unknown;
      version?: unknown;
    };
    return typeof sub === "string" && sub && /^\d+$/.test(String(version))
      ? `${sub}:${version}`
      : undefined;
  } catch {
    return undefined;
  }
}

const readPinCheck = () =>
  read<PinCheck>(
    keys.pinCheck,
    (v) => typeof v.salt === "string" && typeof v.hash === "string",
  );

// Sign-in does not wait for a check to be derived. Reading waits for a save in progress, and a save still running
// when the person is forgotten writes nothing.
let pinCheckEpoch = 0;
let pinCheckSaving: Promise<unknown> = Promise.resolve();
let pinCheckWriting: Promise<unknown> = Promise.resolve();

// Keeps a check of the PIN the server just accepted. A check from the same user at the same security version is of
// this very PIN and is kept. Any other goes at once, since it may be of a PIN changed elsewhere.
export function savePinCheck(
  pin: string,
  accessToken?: string | null,
): Promise<void> {
  const epoch = ++pinCheckEpoch;
  const stamp = accessToken ? tokenStamp(accessToken) : undefined;
  const save = (async () => {
    const current = await readPinCheck();
    if (stamp && current?.stamp === stamp) return;
    if (current) await vault.remove(keys.pinCheck);
    const salt = hexBytes(Crypto.getRandomBytes(16));
    const hash = await pbkdf2(pin, salt);
    if (epoch !== pinCheckEpoch) return;
    const writing = write(keys.pinCheck, {
      version: PIN_CHECK_VERSION,
      salt,
      hash,
      ...(stamp && { stamp }),
    });
    pinCheckWriting = writing.catch(() => undefined);
    await writing;
  })();
  pinCheckSaving = save.catch(() => undefined);
  return save;
}

export async function matchesPinCheck(
  pin: string,
  signal?: AbortSignal,
): Promise<boolean | null> {
  await pinCheckSaving;
  const check = await readPinCheck();
  if (!check) return null;
  const v = check.version ?? 1;
  if (v === 1) return (await digestV1(check.salt, pin)) === check.hash;
  return (await pbkdf2(pin, check.salt, signal)) === check.hash;
}

// Starts checking a PIN against this phone's own check the moment it is complete, alongside the request to the
// server, so that if the server cannot be reached the answer is already there instead of taking seconds more.
// Cancel it once the server has answered.
export function startPinMatch(pin: string): {
  result: Promise<boolean | null>;
  cancel: () => void;
} {
  const controller = new AbortController();
  const result = matchesPinCheck(pin, controller.signal);
  result.catch(() => undefined);
  return { result, cancel: () => controller.abort() };
}

export async function loadOfflineTries(): Promise<OfflineTries> {
  return (
    (await read<OfflineTries>(
      keys.offlineTries,
      (value) =>
        Number.isInteger(value.count) &&
        value.count >= 0 &&
        Number.isFinite(value.pausedUntil) &&
        value.pausedUntil >= 0,
    )) ?? { count: 0, pausedUntil: 0 }
  );
}

export async function saveOfflineTries(tries: OfflineTries): Promise<void> {
  if (!tries.count && !tries.pausedUntil) await vault.remove(keys.offlineTries);
  else await write(keys.offlineTries, tries);
}

export interface StoredCaptureVehicle {
  id: string;
  registration: string;
  companyName: string;
  // The dates still open to capture, in order.
  days: string[];
}

export interface StoredCaptureList {
  owner: string;
  weekStart: string;
  weekThrough: string;
  currentWeekStart: string;
  businessDate: string;
  vehicles: StoredCaptureVehicle[];
  savedAt: number;
}

export async function saveCaptureList(list: StoredCaptureList): Promise<void> {
  await write(keys.captureList, list);
}

export async function loadCaptureList(
  owner: string,
): Promise<StoredCaptureList | null> {
  const list = await read<StoredCaptureList>(
    keys.captureList,
    (value) =>
      typeof value.owner === "string" &&
      value.owner.length > 0 &&
      typeof value.weekStart === "string" &&
      typeof value.weekThrough === "string" &&
      typeof value.currentWeekStart === "string" &&
      typeof value.businessDate === "string" &&
      Number.isFinite(value.savedAt) &&
      Array.isArray(value.vehicles) &&
      value.vehicles.every(
        (vehicle) =>
          typeof vehicle.id === "string" &&
          typeof vehicle.registration === "string" &&
          typeof vehicle.companyName === "string" &&
          Array.isArray(vehicle.days) &&
          vehicle.days.every((day) => typeof day === "string"),
      ),
  );
  if (!list) return null;
  if (list.owner !== owner || Date.now() - list.savedAt > OFFLINE_UNLOCK_MS) {
    await vault.remove(keys.captureList);
    return null;
  }
  return list;
}

// Switch user: this phone stops being trusted for anyone
export async function forgetPerson(): Promise<void> {
  pinCheckEpoch++;
  await pinCheckWriting;
  for (const key of [
    keys.session,
    keys.person,
    keys.pinCheck,
    keys.offlineTries,
    keys.captureList,
  ])
    await vault.remove(key);
}
