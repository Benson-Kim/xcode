import { useEffect, useState } from "react";
import { AppState, Linking } from "react-native";

// A newer build of the app published on GitHub. CI writes version.json next to each APK and builds the app with its
// own build number and that file's address; builds from a laptop have neither and never look for updates.
export type AvailableUpdate = { build: number; version: string; url: string };

export type UpdateSource = { build: number; manifestUrl: string };

export type BuildValues = {
  distribution?: string;
  build?: string;
  updateUrl?: string;
};

// The App Store and Play Store update the app themselves and forbid it from installing builds of its own.
export const releaseSource = ({
  distribution,
  build,
  updateUrl,
}: BuildValues): UpdateSource => ({
  build: Number(build ?? ""),
  manifestUrl: distribution === "store" ? "" : (updateUrl ?? ""),
});

export const RELEASE = releaseSource({
  distribution: process.env.EXPO_PUBLIC_DISTRIBUTION,
  build: process.env.EXPO_PUBLIC_BUILD_NUMBER,
  updateUrl: process.env.EXPO_PUBLIC_UPDATE_URL,
});

const CHECK_EVERY_MS = 60 * 60 * 1000;

export async function checkForUpdate(
  source: UpdateSource,
  fetcher: typeof fetch = fetch,
): Promise<AvailableUpdate | null> {
  if (!source.manifestUrl.startsWith("https://")) return null;
  if (!Number.isInteger(source.build) || source.build <= 0) return null;
  try {
    const response = await fetcher(`${source.manifestUrl}?t=${Date.now()}`, {
      headers: { "Cache-Control": "no-cache" },
    });
    if (!response.ok) return null;
    const body = (await response.json()) as Partial<
      Record<keyof AvailableUpdate, unknown>
    >;
    const { build, version, url } = body;
    if (
      typeof build !== "number" ||
      !Number.isInteger(build) ||
      build <= source.build ||
      typeof url !== "string" ||
      !url.startsWith("https://")
    )
      return null;
    return {
      build,
      version: typeof version === "string" ? version : String(build),
      url,
    };
  } catch {
    return null;
  }
}

// Looks when the app opens and again when it comes back, at most once an hour.
export function useAvailableUpdate(
  source: UpdateSource = RELEASE,
  fetcher: typeof fetch = fetch,
): AvailableUpdate | null {
  const [update, setUpdate] = useState<AvailableUpdate | null>(null);
  useEffect(() => {
    let active = true;
    let checkedAt = 0;
    function check() {
      if (Date.now() - checkedAt < CHECK_EVERY_MS) return;
      checkedAt = Date.now();
      void checkForUpdate(source, fetcher).then(
        (found) => active && found && setUpdate(found),
      );
    }
    check();
    const listener = AppState.addEventListener("change", (next) => {
      if (next === "active") check();
    });
    return () => {
      active = false;
      listener.remove();
    };
  }, [source, fetcher]);
  return update;
}

// Android downloads the APK and offers to install it over this one; nothing is lost on the phone.
export const installUpdate = (update: AvailableUpdate) =>
  Linking.openURL(update.url);
