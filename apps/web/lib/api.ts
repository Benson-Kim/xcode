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

// What this browser remembers (the proxy's cookies, nothing upstream): a trusted device starts at the PIN with the
// person's name.
export type DeviceState = {
  trusted: boolean;
  phoneNumber?: string;
  firstName?: string;
  lastName?: string;
  role?: string;
};

export async function readDevice(): Promise<DeviceState> {
  try {
    const response = await checkedFetch("/api/auth/device", {
      cache: "no-store",
    });
    if (!response.ok) return { trusted: false };
    const state = (await response.json()) as DeviceState;
    return state.trusted === true ? state : { trusted: false };
  } catch {
    return { trusted: false };
  }
}
