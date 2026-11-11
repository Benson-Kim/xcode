import type { Metadata } from "next";
import { connection } from "next/server";

import type { StoreLinks } from "../../components/InvitePanel";
import { InviteScreen } from "../../components/InviteScreen";

export const metadata: Metadata = {
  title: "Set up XCODE",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};

const https = (value: string | undefined) => {
  try {
    return value && new URL(value).protocol === "https:" ? value : undefined;
  } catch {
    return undefined;
  }
};

// Where an invitation link lands (/invite#<token>). Rendered per request, like the sign-in page, so its scripts carry
// the nonce of this response's policy; next.config.ts adds no-referrer and no-store for this path.
export default async function Invite() {
  await connection();
  const stores: StoreLinks = {
    appStore: https(process.env.APP_STORE_URL),
    playStore: https(process.env.PLAY_STORE_URL),
  };
  return <InviteScreen stores={stores} />;
}
