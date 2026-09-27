// The browser preview has no Keychain. It keeps state for the tab only, which is fine for trying the app out and is not a place for real sessions: phones use vault.ts.
export const vault = {
  get: async (key: string) => sessionStorage.getItem(key),
  set: async (key: string, value: string) => sessionStorage.setItem(key, value),
  remove: async (key: string) => sessionStorage.removeItem(key),
};
