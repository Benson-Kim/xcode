import { useCallback, useEffect, useState } from "react";
import { Linking } from "react-native";

import { webUrl } from "../lib/webUrl";
import { inviteTokenFrom } from "./inviteLink";

// The invitation link that opened the app, or came while it was open, until the sign-in screens take it.
export function useInviteLink(): [string | null, () => void] {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    let mounted = true;
    const take = (url: string | null) => {
      const found = inviteTokenFrom(url, webUrl);
      if (found && mounted) setToken(found);
    };
    Linking.getInitialURL().then(take, () => undefined);
    const subscription = Linking.addEventListener("url", ({ url }) =>
      take(url),
    );
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);
  return [token, useCallback(() => setToken(null), [])];
}
