// An in-memory Keychain, so storage runs for real in tests.
jest.mock("expo-secure-store", () => {
  const items = new Map<string, string>();
  return {
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: "when-unlocked-this-device-only",
    __items: items,
    getItemAsync: jest.fn(async (key: string) => items.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => void items.set(key, value)),
    deleteItemAsync: jest.fn(async (key: string) => void items.delete(key)),
  };
});
jest.mock("expo-crypto", () => ({
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  randomUUID: () => "stable-test-device",
  getRandomBytes: (size: number) => new Uint8Array(size).fill(7),
  // Deterministic and one-way enough for tests: the stored check must never contain the PIN.
  digestStringAsync: async (_algorithm: string, value: string) => [...value].reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) >>> 0, 7).toString(16),
}));
jest.mock("expo-network", () => ({ useNetworkState: () => ({ isConnected: true, isInternetReachable: true }) }));
jest.mock("@expo-google-fonts/figtree", () => ({
  useFonts: () => [true, null],
  Figtree_400Regular: 1,
  Figtree_500Medium: 2,
  Figtree_600SemiBold: 3,
  Figtree_700Bold: 4,
}));
jest.mock("react-native-svg", () => {
  const React = require("react");
  const { View } = require("react-native");
  const Shape = ({ children }: { children?: React.ReactNode }) => React.createElement(View, null, children);
  return { __esModule: true, default: Shape, Svg: Shape, Circle: Shape, Path: Shape, Rect: Shape };
});
jest.mock("react-native-safe-area-context", () => {
  const React = require("react");
  const { View } = require("react-native");
  return {
    SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
    SafeAreaView: ({ children, style }: { children: React.ReactNode; style?: unknown }) => React.createElement(View, { style }, children),
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
  };
});

beforeEach(() => {
  require("expo-secure-store").__items.clear();
});
