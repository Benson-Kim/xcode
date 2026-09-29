import * as SecureStore from "expo-secure-store";
import { clearSession, forgetPerson, getDeviceId, loadPerson, loadSession, matchesPinCheck, savePerson, savePinCheck, savePinPolicy, saveSession } from "../src/lib/storage";

const session = { phoneNumber: "0712345678", accessToken: "jwt", refreshToken: "refresh" };

it("keeps session tokens in device-only secure storage", async () => {
  await saveSession(session);
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith("xcode.session", JSON.stringify(session), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  expect(await loadSession()).toEqual(session);
  await clearSession();
  expect(await loadSession()).toBeNull();
});

it("discards malformed session state", async () => {
  await SecureStore.setItemAsync("xcode.session", "not json");
  expect(await loadSession()).toBeNull();
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith("xcode.session", expect.any(Object));
});

it("discards incomplete identity and token state", async () => {
  await SecureStore.setItemAsync("xcode.session", JSON.stringify({ ...session, accessToken: "" }));
  expect(await loadSession()).toBeNull();

  await SecureStore.setItemAsync("xcode.person", JSON.stringify({
    phoneNumber: session.phoneNumber,
    firstName: "Wanjiru",
    lastName: "Kamau",
    role: "Revenue clerk",
    permissions: [],
    pinLength: 3,
  }));
  expect(await loadPerson()).toBeNull();
});

it("checks a PIN offline without storing it", async () => {
  expect(await matchesPinCheck("2580")).toBeNull();
  await savePinCheck("2580");
  expect(await matchesPinCheck("2580")).toBe(true);
  expect(await matchesPinCheck("2581")).toBe(false);
  expect(await SecureStore.getItemAsync("xcode.pin-check")).not.toContain("2580");
});

it("switch user forgets the person but keeps the installation id", async () => {
  const device = await getDeviceId();
  await saveSession(session);
  await savePerson({ phoneNumber: session.phoneNumber, firstName: "Wanjiru", lastName: "Kamau", role: "Revenue clerk", permissions: [], pinLength: 4, lockoutThreshold: 5, lockoutMinutes: 15 });
  await savePinCheck("2580");
  await forgetPerson();
  expect(await loadSession()).toBeNull();
  expect(await matchesPinCheck("2580")).toBeNull();
  expect(await getDeviceId()).toBe(device);
});

it("concurrent requests share a single persistent installation identifier", async () => {
  await jest.isolateModulesAsync(async () => {
    const store = require("expo-secure-store");
    const { getDeviceId: fresh } = require("../src/lib/storage");
    expect(await Promise.all([fresh(), fresh()])).toEqual(["stable-test-device", "stable-test-device"]);
    expect(store.setItemAsync).toHaveBeenCalledTimes(1);
  });
});

it("keeps the organization's wrong-PIN policy with the person, and reads older records as 5 tries and 15 minutes", async () => {
  const person = { phoneNumber: session.phoneNumber, firstName: "Wanjiru", lastName: "Kamau", role: "Revenue clerk", permissions: [], pinLength: 4 };
  // Saved by a phone from before the policy was kept.
  await SecureStore.setItemAsync("xcode.person", JSON.stringify(person));
  expect(await loadPerson()).toEqual({ ...person, lockoutThreshold: 5, lockoutMinutes: 15 });

  await savePinPolicy({ lockoutThreshold: 3, lockoutMinutes: 60 });
  expect(await loadPerson()).toEqual({ ...person, lockoutThreshold: 3, lockoutMinutes: 60 });

  // Outside the organization's bounds (3 to 10 tries, 1 to 60 minutes) the record is not trusted.
  await SecureStore.setItemAsync("xcode.person", JSON.stringify({ ...person, lockoutThreshold: 2, lockoutMinutes: 15 }));
  expect(await loadPerson()).toBeNull();
});
