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

export function useConnected() {
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let active = true;
    getNetworkStateAsync().then(
      (network) => active && setConnected(hasConnection(network)),
      () => {},
    );
    const listener = addNetworkStateListener(
      (network) => active && setConnected(hasConnection(network)),
    );
    return () => {
      active = false;
      listener.remove();
    };
  }, []);
  return connected;
}
