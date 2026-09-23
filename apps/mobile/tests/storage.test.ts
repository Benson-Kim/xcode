import * as SecureStore from "expo-secure-store";
import {
  clearSession,
  getDeviceId,
  loadSession,
  saveSession,
} from "../src/storage";

it("uses device-only secure storage for session tokens without storing a PIN", async () => {
  const session = {
    email: "person@example.com",
    accessToken: "jwt",
    refreshToken: "refresh",
  };
  await saveSession(session);
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
    "xcode.session",
    JSON.stringify(session),
    { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY },
  );
  jest
    .mocked(SecureStore.getItemAsync)
    .mockResolvedValueOnce(JSON.stringify(session));
  expect(await loadSession()).toEqual(session);
  await clearSession();
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
    "xcode.session",
    expect.any(Object),
  );
});
it("discards malformed session state", async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValueOnce("not json");
  expect(await loadSession()).toBeNull();
  expect(SecureStore.deleteItemAsync).toHaveBeenCalled();
});
it("concurrent requests share a single persistent installation identifier", async () => {
  jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  expect(await Promise.all([getDeviceId(), getDeviceId()])).toEqual([
    "stable-test-device",
    "stable-test-device",
  ]);
  expect(SecureStore.setItemAsync).toHaveBeenCalledTimes(1);
});
