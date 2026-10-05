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
// nonce because the policy in proxy.ts names no other script source.
const PRE_PAINT =
  "try{var t=localStorage.getItem('xcode.theme');" +
  "if(t!=='light'&&t!=='dark')t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';" +
  "document.documentElement.dataset.theme=t}catch(e){}";

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en-GB">
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: PRE_PAINT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
