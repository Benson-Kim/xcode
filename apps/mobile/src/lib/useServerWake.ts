import { useEffect } from "react";
import { AppState } from "react-native";

import { wakeServer } from "./api";
import { primeConnection } from "./network";

// The server may have gone to sleep: it wakes as the app opens and each time the app comes back to the front, while
// the person reaches for their PIN. The phone's connection is asked for once, so the first banner already knows it.
export function useServerWake() {
  useEffect(() => {
    wakeServer();
    void primeConnection();
    const listener = AppState.addEventListener("change", (next) => {
      if (next === "active") wakeServer();
    });
    return () => listener.remove();
  }, []);
}
