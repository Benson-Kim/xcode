import { useNetworkState } from "expo-network";

// Unknown counts as online: only an explicit "no" says the phone cannot reach the network.
export function useOnline() {
  const network = useNetworkState();
  return network.isConnected !== false && network.isInternetReachable !== false;
}
