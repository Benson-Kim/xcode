"use client";

import dynamic from "next/dynamic";

import { AuthFrame } from "./auth/AuthFrame";
import type { StoreLinks } from "./InvitePanel";

// The invitation reads its token from the address bar, which only the browser has: it is never rendered on the server.
const InvitePanel = dynamic(
  () => import("./InvitePanel").then((module) => module.InvitePanel),
  {
    ssr: false,
    loading: () => (
      <AuthFrame>
        <section aria-busy="true" className="box">
          <h1>Set up XCODE</h1>
          <div className="muted">Opening your invitation...</div>
        </section>
      </AuthFrame>
    ),
  },
);

export function InviteScreen({ stores }: { stores: StoreLinks }) {
  return <InvitePanel stores={stores} />;
}
