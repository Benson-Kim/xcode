import * as SecureStore from "expo-secure-store";
import * as Crypto from "expo-crypto";
import type { SessionTokens } from "@xcode/shared";

const options = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};
const sessionKey = "xcode.session";
const deviceKey = "xcode.device";

export interface StoredSession extends SessionTokens {
  phoneNumber: string;
}

let devicePromise: Promise<string> | undefined;

export function getDeviceId(): Promise<string> {
  if (!devicePromise)
    devicePromise = (async () => {
      const existing = await SecureStore.getItemAsync(deviceKey, options);
      if (existing) return existing;
      const id = Crypto.randomUUID();
      await SecureStore.setItemAsync(deviceKey, id, options);
      return id;
    })().catch((error) => {
      devicePromise = undefined;
      throw error;
    });
  return devicePromise;
}

export async function saveSession(session: StoredSession): Promise<void> {
  // No PIN is persisted. Keychain/Keystore stores only session tokens and the phone number.
  await SecureStore.setItemAsync(sessionKey, JSON.stringify(session), options);
}

export async function loadSession(): Promise<StoredSession | null> {
  const value = await SecureStore.getItemAsync(sessionKey, options);
  if (!value) return null;
  try {
    const session = JSON.parse(value) as StoredSession;
    if (
      typeof session.phoneNumber === "string" &&
      typeof session.accessToken === "string" &&
      typeof session.refreshToken === "string"
    )
      return session;
  } catch {
    /* Corrupted state is cleared rather than trusted. */
  }
  await clearSession();
  return null;
}

export async function clearSession(): Promise<void> {
  await SecureStore.deleteItemAsync(sessionKey, options);
}
