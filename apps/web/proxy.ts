import { NextRequest, NextResponse } from "next/server";

// A nonce-based policy, which needs every page rendered per request (app/page.tsx awaits connection()).
// XCODE is an authenticated shell behind sign-in, so nothing here is cached or served from a CDN and
// dynamic rendering costs nothing. Styles keep 'unsafe-inline': Tailwind's runtime writes inline style
// attributes that a nonce cannot cover. Development adds 'unsafe-eval', which React needs to rebuild
// server error stacks in the browser.
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const development = process.env.NODE_ENV === "development";
  const policy = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    // Google Fonts serves the brand face: the stylesheet is a style source, the font files a font source.
    // Nothing else is fetched from off-origin, and a blocked stylesheet would silently fall back to Segoe UI.
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob:",
    "font-src 'self' https://fonts.gstatic.com",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    // Only in production, so that local development over http is not upgraded to https.
    ...(development ? [] : ["upgrade-insecure-requests"]),
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", policy);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      // The API proxies return JSON, and static assets need no policy. Prefetches are skipped so that
      // a prefetched page is never cached with another request's nonce.
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
