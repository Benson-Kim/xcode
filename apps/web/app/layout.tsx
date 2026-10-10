import type { Metadata } from "next";
import { headers } from "next/headers";

import "./globals.css";

export const metadata: Metadata = {
  title: "XCODE",
  description: "Fleet finance",
};

// The theme the browser last painted, read before React runs so that a person who chose the dark theme does not
// see a light page flash on every load. applyAppearance writes it; the shell replaces it once the appearance
// arrives, which is the only thing that can tell us what the organization allows. The script carries the request's
// nonce because the policy in proxy.ts names no other script source. It sets data-theme on <html> before hydration,
// so that element alone is told the server's attributes may differ (React checks it one level deep only).
const PRE_PAINT =
  "try{var t=localStorage.getItem('xcode.theme');" +
  "if(t!=='light'&&t!=='dark')t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';" +
  "document.documentElement.dataset.theme=t}catch(e){}";

const FONTS =
  "https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800;900&family=Fraunces:opsz,wght@9..144,700&display=swap";

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en-GB" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: PRE_PAINT }} />
        {/* The brand faces: Figtree throughout, Fraunces for the wordmark. A CSS @import of this stylesheet is dropped
            by the build, so it is linked here; the policy in proxy.ts allows this host and its font files. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link rel="stylesheet" href={FONTS} />
      </head>
      <body>{children}</body>
    </html>
  );
}
