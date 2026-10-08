import type { NextConfig } from "next";
import path from "node:path";
const config: NextConfig = {
  transpilePackages: ["@xcode/shared"],
  poweredByHeader: false,
  // The development server only serves its scripts and live reload to localhost unless told otherwise. A phone on the
  // local network opens it by this computer's address, e.g. DEV_ORIGINS=192.168.100.9. Production builds ignore it.
  allowedDevOrigins: (process.env.DEV_ORIGINS ?? "")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean),
  // A worktree whose node_modules links to packages installed in another checkout needs Turbopack's root to hold both,
  // e.g. TURBOPACK_ROOT=C:\Users\me\Code; Turbopack refuses links that lead outside its root. Unset, Next.js chooses.
  ...(process.env.TURBOPACK_ROOT
    ? { turbopack: { root: process.env.TURBOPACK_ROOT } }
    : {}),
  // The web Dockerfile sets NEXT_OUTPUT=standalone; the root is the monorepo so the shared package is traced.
  ...(process.env.NEXT_OUTPUT === "standalone"
    ? {
        output: "standalone" as const,
        outputFileTracingRoot:
          process.env.TURBOPACK_ROOT ?? path.join(process.cwd(), "..", ".."),
      }
    : {}),
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          // Browsers keep to HTTPS for a year once they have seen this, so it is only sent by production builds.
          ...(process.env.NODE_ENV === "production"
            ? [
                {
                  key: "Strict-Transport-Security",
                  value: "max-age=31536000; includeSubDomains",
                },
              ]
            : []),
        ],
      },
    ];
  },
};
export default config;
