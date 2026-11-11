// The files the phones fetch to trust this site's invitation links to open the app. Each is null until its setting
// is present and well formed, and the route then answers 404, so a typo never publishes a wrong association.
const INVITE_PATH = "/invite";
const ANDROID_PACKAGE = "ke.co.priori.xcode";

export function appleAppSiteAssociation(
  env: Record<string, string | undefined> = process.env,
) {
  const appId = env.IOS_APP_ID?.trim() ?? "";
  if (!/^[A-Z0-9]{10}\.[A-Za-z0-9.-]+$/.test(appId)) return null;
  return {
    applinks: {
      details: [{ appIDs: [appId], components: [{ "/": INVITE_PATH }] }],
    },
  };
}

export function androidAssetLinks(
  env: Record<string, string | undefined> = process.env,
) {
  const fingerprints = (env.ANDROID_CERT_SHA256 ?? "")
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);
  if (
    !fingerprints.length ||
    !fingerprints.every((value) =>
      /^([0-9A-F]{2}:){31}[0-9A-F]{2}$/.test(value),
    )
  )
    return null;
  return [
    {
      relation: ["delegate_permission/common.handle_all_urls"],
      target: {
        namespace: "android_app",
        package_name: ANDROID_PACKAGE,
        sha256_cert_fingerprints: fingerprints,
      },
    },
  ];
}

// A published file is public and changes only with a release, so the phones and Apple's CDN may keep it for an hour.
// A 404 is never kept, so a fixed setting is seen at once.
export function associationResponse(document: object | null) {
  return document
    ? Response.json(document, {
        headers: { "Cache-Control": "public, max-age=3600" },
      })
    : new Response(null, {
        status: 404,
        headers: { "Cache-Control": "no-store" },
      });
}
