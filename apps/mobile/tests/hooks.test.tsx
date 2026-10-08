import { renderHook } from "@testing-library/react-native";

import { useOnline } from "../src/lib/network";
import { useLatest } from "../src/lib/useLatest";

describe("useLatest", () => {
  it("returns the newest value after a rerender", async () => {
    const { result, rerender } = await renderHook(
      (value: string) => useLatest(value),
      { initialProps: "first" },
    );
    expect(result.current.current).toBe("first");
    await rerender("second");
    expect(result.current.current).toBe("second");
  });

  it("keeps one ref for the life of the component", async () => {
    const { result, rerender } = await renderHook(
      (value: number) => useLatest(value),
      { initialProps: 1 },
    );
    const first = result.current;
    await rerender(2);
    expect(result.current).toBe(first);
  });
});

describe("useOnline", () => {
  const network = (state: {
    isConnected?: boolean;
    isInternetReachable?: boolean;
  }) =>
    jest
      .spyOn(require("expo-network"), "useNetworkState")
      .mockReturnValue(state);

  afterEach(() => jest.restoreAllMocks());

  it.each([
    [{ isConnected: true, isInternetReachable: true }, true],
    [{ isConnected: false, isInternetReachable: true }, false],
    [{ isConnected: true, isInternetReachable: false }, false],
    [{ isConnected: false, isInternetReachable: false }, false],
    [{}, true],
    [{ isConnected: true }, true],
    [{ isInternetReachable: undefined }, true],
  ])("reads %j as online: %s", async (state, online) => {
    network(state);
    const { result } = await renderHook(() => useOnline());
    expect(result.current).toBe(online);
  });
});
