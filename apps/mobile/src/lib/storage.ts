import * as Crypto from "expo-crypto";
import type { SessionTokens } from "@xcode/shared";
import { vault } from "./vault";

const keys = {
  device: "xcode.device",
  session: "xcode.session",
  person: "xcode.person",
  pinCheck: "xcode.pin-check",
  offlineTries: "xcode.offline-tries",
};

export interface StoredSession extends SessionTokens {
  phoneNumber: string;
}

// Who this phone is trusted for, kept so the unlock screen can greet them and the app can open offline.
export interface StoredPerson {
  phoneNumber: string;
  firstName: string;
  lastName: string;
  role: string;
  permissions: string[];
  pinLength: number;
}

// Wrong PINs typed while offline, and when the resulting pause ends.
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

async function read<T>(
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
      session.refreshToken.length > 0,
  );
}

export async function clearSession(): Promise<void> {
  await vault.remove(keys.session);
}

export async function savePerson(person: StoredPerson): Promise<void> {
  await write(keys.person, person);
}

export function loadPerson() {
  return read<StoredPerson>(
    keys.person,
    (person) =>
      typeof person.phoneNumber === "string" &&
      person.phoneNumber.length > 0 &&
      typeof person.firstName === "string" &&
      person.firstName.length > 0 &&
      typeof person.lastName === "string" &&
      person.lastName.length > 0 &&
      typeof person.role === "string" &&
      person.role.length > 0 &&
      Array.isArray(person.permissions) &&
      person.permissions.every((permission) => typeof permission === "string") &&
      Number.isInteger(person.pinLength) &&
      person.pinLength >= 4 &&
      person.pinLength <= 8,
  );
}

// The PIN itself is never stored: only a salted SHA-256 of it, so a PIN typed offline can be checked.
// A four-digit PIN is quick to guess from its hash, so what protects it is the device-only keychain and the pause after five wrong tries, not the hash.
async function digest(salt: string, pin: string) {
  return Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    `${salt}:${pin}`,
  );
}

export async function savePinCheck(pin: string): Promise<void> {
  const salt = Array.from(Crypto.getRandomBytes(16), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  await write(keys.pinCheck, { salt, hash: await digest(salt, pin) });
}

// true or false once a check is stored; null when this phone has none (it has never signed in online).
export async function matchesPinCheck(pin: string): Promise<boolean | null> {
  const check = await read<{ salt: string; hash: string }>(
    keys.pinCheck,
    (value) => typeof value.salt === "string" && typeof value.hash === "string",
  );
  if (!check) return null;
  return (await digest(check.salt, pin)) === check.hash;
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

// Switch user: this phone stops being trusted for anyone. The device id stays; it names the install.
export async function forgetPerson(): Promise<void> {
  await Promise.all(
    [keys.session, keys.person, keys.pinCheck, keys.offlineTries].map((key) =>
      vault.remove(key),
    ),
  );
}
