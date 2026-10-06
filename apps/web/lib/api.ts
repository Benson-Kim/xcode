import { createAuthClient } from "@xcode/shared/auth";

import { checkedFetch } from "./checkedFetch";

export const authApi = createAuthClient("/api/auth", checkedFetch);
