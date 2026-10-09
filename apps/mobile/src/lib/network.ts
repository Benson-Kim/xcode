import {
  addNetworkStateListener,
  getNetworkStateAsync,
  useNetworkState,
} from "expo-network";
import { useEffect, useState } from "react";

export function useOnline() {
  const network = useNetworkState();
  return network.isConnected !== false && network.isInternetReachable !== false;
}

export const hasConnection = (network: {
  isConnected?: boolean;
  isInternetReachable?: boolean;
}) => network.isConnected === true && network.isInternetReachable !== false;

// The connection the phone last reported. A banner that opens later starts from it, rather than saying "No
// internet" until the phone answers and then switching to "Can't reach the XCODE server".
let lastKnown: boolean | null = null;

const remember = (network: Parameters<typeof hasConnection>[0]) =>
  (lastKnown = hasConnection(network));

// Asked once as the app opens, so the first banner already knows.
export function primeConnection(): Promise<void> {
  return getNetworkStateAsync().then(
    (network) => void remember(network),
    () => undefined,
  );
}

export function useConnected() {
  const [connected, setConnected] = useState(lastKnown ?? true);
  useEffect(() => {
    let active = true;
    getNetworkStateAsync().then(
      (network) => active && setConnected(remember(network)),
      () => {},
    );
    const listener = addNetworkStateListener(
      (network) => active && setConnected(remember(network)),
    );
    return () => {
      active = false;
      listener.remove();
    };
  }, []);
  return connected;
}
