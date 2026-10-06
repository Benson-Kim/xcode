// An in-memory Keychain, so storage runs for real in tests.
jest.mock("expo-secure-store", () => {
  const items = new Map<string, string>();
  return {
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: "when-unlocked-this-device-only",
    __items: items,
    getItemAsync: jest.fn(async (key: string) => items.get(key) ?? null),
    setItemAsync: jest.fn(
      async (key: string, value: string) => void items.set(key, value),
    ),
    deleteItemAsync: jest.fn(async (key: string) => void items.delete(key)),
  };
});
jest.mock("expo-crypto", () => ({
  CryptoDigestAlgorithm: { SHA256: "SHA-256" },
  randomUUID: () => "stable-test-device",
  getRandomBytes: (size: number) => new Uint8Array(size).fill(7),
  digestStringAsync: async (_algorithm: string, value: string) =>
    [...value]
      .reduce((hash, char) => (hash * 31 + char.charCodeAt(0)) >>> 0, 7)
      .toString(16),
}));
// The real derivation runs in pbkdf2.test.ts and storage.test.ts; flows use one iteration.
jest.mock("../src/lib/pbkdf2", () => {
  const actual = jest.requireActual("../src/lib/pbkdf2");
  return {
    pbkdf2Sha256: (password: Uint8Array, salt: Uint8Array) =>
      actual.pbkdf2Sha256(password, salt, 1),
  };
});

// Tests announce a change of network with require("expo-network").__emit(state).
jest.mock("expo-network", () => {
  // Names inside a mock factory must start with "mock" to be allowed there.
  const listeners = new Set<
    (mockState: {
      isConnected?: boolean;
      isInternetReachable?: boolean;
    }) => void
  >();
  return {
    useNetworkState: () => ({ isConnected: true, isInternetReachable: true }),
    addNetworkStateListener: (
      listener: (mockState: {
        isConnected?: boolean;
        isInternetReachable?: boolean;
      }) => void,
    ) => {
      listeners.add(listener);
      return { remove: () => listeners.delete(listener) };
    },
    __emit: (mockState: {
      isConnected?: boolean;
      isInternetReachable?: boolean;
    }) => listeners.forEach((listener) => listener(mockState)),
  };
});

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
  const Shape = ({ children }: { children?: React.ReactNode }) =>
    React.createElement(View, null, children);
  return {
    __esModule: true,
    default: Shape,
    Svg: Shape,
    Circle: Shape,
    Path: Shape,
    Rect: Shape,
  };
});

jest.mock("react-native-safe-area-context", () => {
  const React = require("react");
  const { View } = require("react-native");
  return {
    SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
    SafeAreaView: ({
      children,
      style,
    }: {
      children: React.ReactNode;
      style?: unknown;
    }) => React.createElement(View, { style }, children),
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
  };
});

// A cold run transforms React Native's lazily loaded components during the first render. That work blocks
// the event loop for seconds (a minute on a busy machine), so whichever test rendered first used to time out.
// One render here, with its own allowance, pays for it before any test starts. The library is loaded here, not
// inside the hook, because it registers its own hooks when first loaded.
const { render } = require("@testing-library/react-native");
beforeAll(async () => {
  if (!expect.getState().testPath?.endsWith(".tsx")) return;
  const React = require("react");
  // Also the components that later screens load on first use: the revenue lists and the capture sheet.
  const native = require("react-native");
  for (const name of [
    "FlatList",
    "Modal",
    "KeyboardAvoidingView",
    "ScrollView",
    "TextInput",
    "Pressable",
    "ActivityIndicator",
    "Image",
  ])
    void native[name];
  const App = require("../App").default;
  const view = await render(React.createElement(App));
  await view.findByLabelText("Mobile number");
  await view.unmount();
}, 120000);

beforeEach(() => {
  require("expo-secure-store").__items.clear();
});
