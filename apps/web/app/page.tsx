import { connection } from "next/server";

import { AuthPanel } from "../components/AuthPanel";

// Sign-in screens until there is a session, then the app shell.
// Waiting for the request keeps this page out of the build output, so that every response carries the
// nonce its own Content-Security-Policy names (proxy.ts). A prerendered shell would ship script tags
// with no nonce, which 'strict-dynamic' then refuses to run.
export default async function Home() {
  await connection();
  return <AuthPanel />;
}
