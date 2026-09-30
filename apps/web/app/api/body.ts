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
