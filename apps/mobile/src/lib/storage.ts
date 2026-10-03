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

// The organization's wrong-PIN policy: tries before a pause, and the pause. The phone enforces it offline.
export interface PinPolicy {
  lockoutThreshold: number;
  lockoutMinutes: number;
}

// What a phone uses until it has loaded the organization's policy, and for records saved before it kept one.
export const DEFAULT_PIN_POLICY: PinPolicy = { lockoutThreshold: 5, lockoutMinutes: 15 };

// The bounds the API allows: at least three tries, a pause of at most an hour.
export const validPinPolicy = (policy: Partial<PinPolicy>) =>
  Number.isInteger(policy.lockoutThreshold) &&
  policy.lockoutThreshold! >= 3 &&
  policy.lockoutThreshold! <= 10 &&
  Number.isInteger(policy.lockoutMinutes) &&
  policy.lockoutMinutes! >= 1 &&
  policy.lockoutMinutes! <= 60;

// Who this phone is trusted for, kept so the unlock screen can greet them and the app can open offline.
export interface StoredPerson extends PinPolicy {
  // The account's id, which never changes; an admin can change the phone number. Absent on records a Phase 1 app
  // saved: it arrives with the next online sign-in.
  userId?: string;
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
      session.refreshToken.length > 0,
  );
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
      (person.userId === undefined || (typeof person.userId === "string" && person.userId.length > 0)) &&
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
      person.pinLength <= 8 &&
      // Absent on records saved before the policy was kept; those read as the defaults.
      ((person.lockoutThreshold === undefined && person.lockoutMinutes === undefined) || validPinPolicy(person)),
  );
  return person && { ...DEFAULT_PIN_POLICY, ...person };
}

// Keeps the organization's policy (from the appearance) with the person this phone is trusted for.
export async function savePinPolicy(policy: PinPolicy): Promise<void> {
  const person = await loadPerson();
  if (person && validPinPolicy(policy))
    await savePerson({ ...person, lockoutThreshold: policy.lockoutThreshold, lockoutMinutes: policy.lockoutMinutes });
}

// The PIN itself is never stored: only a salted SHA-256 of it, so a PIN typed offline can be checked.
// A four-digit PIN is quick to guess from its hash, so what protects it is the device-only keychain and the pause after the organization's wrong tries, not the hash.
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
// One removal at a time, session and person first: the phone is trusted only while both are kept, so a kill part
// way leaves it trusted for no one, never trusted with its PIN check or wrong-PIN pause gone.
export async function forgetPerson(): Promise<void> {
  for (const key of [keys.session, keys.person, keys.pinCheck, keys.offlineTries])
    await vault.remove(key);
}
