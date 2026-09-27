import * as SecureStore from "expo-secure-store";

// The Keychain (iOS) or Keystore (Android), readable only while this device is unlocked.
const options = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export const vault = {
  get: (key: string) => SecureStore.getItemAsync(key, options),
  set: (key: string, value: string) =>
    SecureStore.setItemAsync(key, value, options),
  remove: (key: string) => SecureStore.deleteItemAsync(key, options),
};
