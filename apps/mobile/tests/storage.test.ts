import * as SecureStore from "expo-secure-store";

import {
  clearSession,
  forgetPerson,
  getDeviceId,
  loadPerson,
  loadSession,
  matchesPinCheck,
  saveOfflineTries,
  savePerson,
  savePinCheck,
  savePinPolicy,
  saveSession,
} from "../src/lib/storage";
import { accessToken } from "./fakeApi";

jest.unmock("../src/lib/pbkdf2");

const pbkdf2 =
  require("../src/lib/pbkdf2") as typeof import("../src/lib/pbkdf2");
const items = () => require("expo-secure-store").__items as Map<string, string>;

const spies: { mockRestore(): void }[] = [];
afterEach(() => spies.splice(0).forEach((spy) => spy.mockRestore()));

function watchDerivations() {
  const derive = jest.spyOn(pbkdf2, "pbkdf2Sha256");
  spies.push(derive);
  return derive;
}

// Holds the next derivation until release() is called.
function holdDerivation() {
  const real = pbkdf2.pbkdf2Sha256;
  let release = () => {};
  const derive = watchDerivations().mockImplementationOnce(
    (...args) =>
      new Promise((resolve) => {
        release = () => resolve(real(...args));
      }),
  );
  return {
    derive,
    release: () => release(),
    started: async () => {
      while (!derive.mock.calls.length)
        await new Promise((resolve) => setTimeout(resolve, 0));
    },
  };
}

const session = {
  phoneNumber: "0712345678",
  accessToken: "jwt",
  refreshToken: "refresh",
};

it("keeps session tokens in device-only secure storage", async () => {
  await saveSession(session);
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
    "xcode.session",
    JSON.stringify(session),
    {
      keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
    },
  );
  expect(await loadSession()).toEqual(session);
  await clearSession();
  expect(await loadSession()).toBeNull();
});

it("discards malformed session state", async () => {
  await SecureStore.setItemAsync("xcode.session", "not json");
  expect(await loadSession()).toBeNull();
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
    "xcode.session",
    expect.any(Object),
  );
});

it("discards incomplete identity and token state", async () => {
  await SecureStore.setItemAsync(
    "xcode.session",
    JSON.stringify({ ...session, accessToken: "" }),
  );
  expect(await loadSession()).toBeNull();

  await SecureStore.setItemAsync(
    "xcode.person",
    JSON.stringify({
      phoneNumber: session.phoneNumber,
      firstName: "Wanjiru",
      lastName: "Kamau",
      role: "Revenue clerk",
      permissions: [],
      pinLength: 3,
    }),
  );
  expect(await loadPerson()).toBeNull();
});

it("checks a PIN offline without storing it", async () => {
  expect(await matchesPinCheck("2580")).toBeNull();
  await savePinCheck("2580");
  expect(await matchesPinCheck("2580")).toBe(true);
  expect(await matchesPinCheck("2581")).toBe(false);
  expect(await SecureStore.getItemAsync("xcode.pin-check")).not.toContain(
    "2580",
  );
});

it("keeps the check without deriving again when the same user signs in at the same security version", async () => {
  await savePinCheck("1379", accessToken("user-1", 3));
  const kept = items().get("xcode.pin-check");
  const derive = watchDerivations();
  await savePinCheck("1379", accessToken("user-1", 3));
  expect(derive).not.toHaveBeenCalled();
  expect(items().get("xcode.pin-check")).toBe(kept);

  // A token the phone cannot read never counts as unchanged.
  await savePinCheck("1379", "not-a-token");
  expect(derive).toHaveBeenCalledTimes(1);
  expect(await matchesPinCheck("1379")).toBe(true);
});

it("drops the old check at once when the PIN may have changed, and keeps the new one once derived", async () => {
  await savePinCheck("1379", accessToken("user-1", 3));
  const held = holdDerivation();
  const saving = savePinCheck("2468", accessToken("user-1", 4));
  await held.started();
  expect(items().has("xcode.pin-check")).toBe(false);
  held.release();
  await saving;
  expect(await matchesPinCheck("2468")).toBe(true);
  expect(await matchesPinCheck("1379")).toBe(false);
});

it("never keeps another user's check, even at the same security version", async () => {
  await savePinCheck("1379", accessToken("user-1", 3));
  await savePinCheck("2468", accessToken("user-2", 3));
  expect(await matchesPinCheck("2468")).toBe(true);
  expect(await matchesPinCheck("1379")).toBe(false);
});

it("checks a PIN against a save still being derived", async () => {
  const held = holdDerivation();
  const saving = savePinCheck("2468", accessToken("user-1", 1));
  await held.started();
  const match = matchesPinCheck("2468");
  held.release();
  expect(await match).toBe(true);
  await saving;
});

it("writes nothing from a save still being derived when switch user forgets the person", async () => {
  const held = holdDerivation();
  const saving = savePinCheck("2468", accessToken("user-1", 1));
  await held.started();
  await forgetPerson();
  held.release();
  await saving;
  expect(items().has("xcode.pin-check")).toBe(false);
  expect(await matchesPinCheck("2468")).toBeNull();
});

it("switch user forgets the person but keeps the installation id", async () => {
  const device = await getDeviceId();
  await saveSession(session);
  await savePerson({
    phoneNumber: session.phoneNumber,
    firstName: "Wanjiru",
    lastName: "Kamau",
    role: "Revenue clerk",
    permissions: [],
    pinLength: 4,
    lockoutThreshold: 5,
    lockoutMinutes: 15,
  });
  await savePinCheck("2580");
  await forgetPerson();
  expect(await loadSession()).toBeNull();
  expect(await matchesPinCheck("2580")).toBeNull();
  expect(await getDeviceId()).toBe(device);
});

it("switch user stops trusting the phone before it forgets the PIN check and the wrong-PIN pause", async () => {
  const items = require("expo-secure-store").__items as Map<string, string>;
  await saveSession(session);
  await savePerson({
    phoneNumber: session.phoneNumber,
    firstName: "Wanjiru",
    lastName: "Kamau",
    role: "Revenue clerk",
    permissions: [],
    pinLength: 4,
    lockoutThreshold: 5,
    lockoutMinutes: 15,
  });
  await savePinCheck("2580");
  await saveOfflineTries({ count: 0, pausedUntil: Date.now() + 15 * 60_000 });
  const before = JSON.stringify([...items]);

  // The app can be killed after any removal, and removals started together may finish in any order: here the
  // last one started finishes first.
  const remove = jest.mocked(SecureStore.deleteItemAsync);
  const original = remove.getMockImplementation()!;
  const started: (() => void)[] = [];
  const states: [string, string][][] = [];
  remove.mockImplementation(
    (key) =>
      new Promise<void>((resolve) => {
        started.push(() => {
          items.delete(key);
          states.push([...items]);
          resolve();
        });
        if (started.length === 1)
          setTimeout(() =>
            started
              .splice(0)
              .reverse()
              .forEach((finish) => finish()),
          );
      }),
  );
  try {
    await forgetPerson();
  } finally {
    remove.mockImplementation(original);
  }
  expect(states.at(-1)).toEqual([]);

  // App.tsx trusts the phone for someone only while the session and the person match. After each removal the phone
  // is either as it was or trusted for no one, never trusted with its PIN check or pause gone.
  const outcomes = [];
  for (const state of states) {
    items.clear();
    for (const [key, value] of state) items.set(key, value);
    const [kept, person] = await Promise.all([loadSession(), loadPerson()]);
    const trusted = kept !== null && person?.phoneNumber === kept.phoneNumber;
    outcomes.push(
      !trusted
        ? "trusted for no one"
        : JSON.stringify([...items]) === before
          ? "as it was"
          : "trusted, with its PIN check or pause gone",
    );
  }
  // Every step, however many keys forgetPerson clears, leaves the phone trusted for no one.
  expect(outcomes).toEqual(states.map(() => "trusted for no one"));
});

it("concurrent requests share a single persistent installation identifier", async () => {
  await jest.isolateModulesAsync(async () => {
    const store = require("expo-secure-store");
    const { getDeviceId: fresh } = require("../src/lib/storage");
    expect(await Promise.all([fresh(), fresh()])).toEqual([
      "stable-test-device",
      "stable-test-device",
    ]);
    expect(store.setItemAsync).toHaveBeenCalledTimes(1);
  });
});

it("verifies a v1 SHA-256 pin check from before the PBKDF2 upgrade", async () => {
  const Crypto = require("expo-crypto");
  const oldHash = await Crypto.digestStringAsync(
    "SHA-256",
    "0707070707070707070707070707070707070707070707070707070707070707:2580",
  );
  await SecureStore.setItemAsync(
    "xcode.pin-check",
    JSON.stringify({
      salt: "0707070707070707070707070707070707070707070707070707070707070707",
      hash: oldHash,
    }),
  );
  expect(await matchesPinCheck("2580")).toBe(true);
  expect(await matchesPinCheck("9999")).toBe(false);
});

it("writes a v2 PBKDF2 pin check and verifies it", async () => {
  await savePinCheck("1379");
  const stored = JSON.parse(
    (require("expo-secure-store").__items as Map<string, string>).get(
      "xcode.pin-check",
    )!,
  );
  expect(stored.version).toBe(2);
  expect(stored.hash).not.toContain("1379");
  expect(await matchesPinCheck("1379")).toBe(true);
  expect(await matchesPinCheck("0000")).toBe(false);
});

it("checks a PIN offline on a phone, which has no WebCrypto", async () => {
  const webCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  Object.defineProperty(globalThis, "crypto", {
    value: undefined,
    configurable: true,
  });
  try {
    await savePinCheck("1379");
    expect(await matchesPinCheck("1379")).toBe(true);
    expect(await matchesPinCheck("1380")).toBe(false);
  } finally {
    if (webCrypto) Object.defineProperty(globalThis, "crypto", webCrypto);
  }
});

it("keeps the organization's wrong-PIN policy with the person, and reads older records as 5 tries and 15 minutes", async () => {
  const person = {
    phoneNumber: session.phoneNumber,
    firstName: "Wanjiru",
    lastName: "Kamau",
    role: "Revenue clerk",
    permissions: [],
    pinLength: 4,
  };
  // Saved by a phone from before the policy was kept.
  await SecureStore.setItemAsync("xcode.person", JSON.stringify(person));
  expect(await loadPerson()).toEqual({
    ...person,
    lockoutThreshold: 5,
    lockoutMinutes: 15,
  });

  await savePinPolicy({ lockoutThreshold: 3, lockoutMinutes: 60 });
  expect(await loadPerson()).toEqual({
    ...person,
    lockoutThreshold: 3,
    lockoutMinutes: 60,
  });

  // Outside the organization's bounds (3 to 10 tries, 1 to 60 minutes) the record is not trusted.
  await SecureStore.setItemAsync(
    "xcode.person",
    JSON.stringify({ ...person, lockoutThreshold: 2, lockoutMinutes: 15 }),
  );
  expect(await loadPerson()).toBeNull();
});
