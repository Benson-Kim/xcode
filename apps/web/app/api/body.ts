import { isIP } from "node:net";
import type { NextRequest } from "next/server";

// The largest body the proxy forwards. The biggest legitimate one is a logo upload, a data URL of about 350 KB.
export const MAX_BODY_BYTES = 1024 * 1024;

// Reads a request body as text, or returns null once it is over the limit: by its declared Content-Length before
// reading anything, and by the bytes actually read, so a missing or false length cannot get past it.
export async function readLimitedBody(request: NextRequest): Promise<string | null> {
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) return null;
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf8");
}

// Names the browser to the API, which limits sign-in tries per client and would otherwise see only this proxy. Next.js
// keeps any x-forwarded-for a client sends, so only the entry the outermost trusted proxy appended is believed: the
// Nth from the right for TRUSTED_PROXY_HOPS = N. At 0 (the default) nothing is forwarded and the API sees this server.
// X-Real-IP and Forwarded are never used. The API believes the header only from a proxy it trusts (KnownProxies).
export function forwardedFor(request: NextRequest): Record<string, string> {
  const setting = process.env.TRUSTED_PROXY_HOPS?.trim() || "0";
  const hops = /^\d+$/.test(setting) ? Number(setting) : 0;
  if (hops === 0) return {};
  const entries = request.headers.get("x-forwarded-for")?.split(",").map((entry) => entry.trim()) ?? [];
  const address = entries.length >= hops ? entries[entries.length - hops] : "";
  return isIP(address) ? { "X-Forwarded-For": address } : {};
}
