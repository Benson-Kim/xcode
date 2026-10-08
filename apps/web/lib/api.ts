import { createAuthClient } from "@xcode/shared/auth";

import { checkedFetch } from "./checkedFetch";
import { clearDataCache } from "./data/cache";

// Any sign-in, sign-out or device change may switch the user: what was cached belonged to the previous one.
const authFetch: typeof fetch = async (input, init) => {
  try {
    return await checkedFetch(input, init);
  } finally {
    clearDataCache();
  }
};

export const authApi = createAuthClient("/api/auth", authFetch);
