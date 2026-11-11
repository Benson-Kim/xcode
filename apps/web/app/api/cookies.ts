// A __Host- cookie is accepted only when Secure, for the whole origin and without a Domain, so no other site under the
// same parent domain can set or shadow it. That rules out a narrower path, even for the refresh token: integrity
// against a sibling site matters more than keeping the token off requests that ignore it.
export const COOKIE = {
  access: "__Host-access",
  refresh: "__Host-refresh",
  device: "__Host-device",
  remember: "__Host-remember",
  trust: "__Host-trust",
  who: "__Host-who",
  invite: "__Host-invite",
} as const;

export type CookieName = keyof typeof COOKIE;

// Browsers accept Secure cookies over plain HTTP only from localhost. A phone on the local network opens the
// development server by this computer's address, so it needs `npm run dev:lan`, which serves HTTPS.
export const cookieOptions = {
  httpOnly: true,
  secure: true,
  sameSite: "strict" as const,
  path: "/",
};

export type CookieJar = {
  get: (name: string) => { value: string } | undefined;
};

type CookieWriter = {
  cookies: {
    has: (name: string) => boolean;
    set: (
      name: string,
      value: string,
      options: typeof cookieOptions & { maxAge?: number },
    ) => unknown;
  };
};

// The unprefixed names that browsers signed in before the move still hold.
const LEGACY: readonly string[] = [
  "access",
  "refresh",
  "device",
  "remember",
  "trust",
  "who",
];

export function readCookie(jar: CookieJar, name: CookieName) {
  return (
    jar.get(COOKIE[name])?.value ||
    (LEGACY.includes(name) ? jar.get(name)?.value : undefined) ||
    undefined
  );
}

// No maxAge leaves a session cookie; 0 expires it.
export function writeCookie(
  output: CookieWriter,
  name: CookieName,
  value: string,
  maxAge?: number,
) {
  output.cookies.set(COOKIE[name], value, {
    ...cookieOptions,
    ...(maxAge === undefined ? {} : { maxAge }),
  });
}

// Moves each unprefixed cookie once: renamed when this answer leaves it alone, then expired. Access and refresh are
// only expired once this answer replaces them: a refresh that lost to another tab must not restore the token it spent,
// and the next refresh moves both anyway.
export function moveLegacyCookies(
  jar: CookieJar,
  output: CookieWriter,
  lifetime: (name: CookieName) => number | undefined,
) {
  for (const name of LEGACY as readonly CookieName[]) {
    const value = jar.get(name)?.value;
    if (value === undefined) continue;
    const replaced =
      output.cookies.has(COOKIE[name]) || jar.get(COOKIE[name]) !== undefined;
    if (!replaced && (name === "access" || name === "refresh")) continue;
    if (!replaced && value) writeCookie(output, name, value, lifetime(name));
    output.cookies.set(name, "", { ...cookieOptions, maxAge: 0 });
  }
}
