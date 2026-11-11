import type { ConfigContext, ExpoConfig } from "expo/config";

export const INVITE_PATH = "/invite";

export interface WebOrigin {
  secure: boolean;
  host: string;
}

const ORIGIN =
  /^(https?):\/\/([a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*)(:\d{1,5})?\/?$/;

// The same value as the API's XCODE_PUBLIC_WEB_URL. Store builds verify their app links against it.
export const webOrigin = (
  url: string | undefined,
  store: boolean,
): WebOrigin | null => {
  if (!url) {
    if (store)
      throw new Error("EXPO_PUBLIC_WEB_URL must be set for store builds.");
    return null;
  }
  const match = ORIGIN.exec(url);
  if (!match)
    throw new Error(
      "EXPO_PUBLIC_WEB_URL must be a lower-case origin with no path, query or fragment.",
    );
  const secure = match[1] === "https";
  const port = match[6];
  if (store && (!secure || port))
    throw new Error(
      "EXPO_PUBLIC_WEB_URL must be an HTTPS origin with no port for store builds.",
    );
  return { secure: secure && !port, host: match[2] };
};

// Only a verified HTTPS link to the invitation page opens the app; no custom scheme carries the token.
export const withInviteLinks = (
  config: ExpoConfig,
  env: Record<string, string | undefined>,
): ExpoConfig => {
  const origin = webOrigin(
    env.EXPO_PUBLIC_WEB_URL,
    env.EXPO_PUBLIC_DISTRIBUTION === "store",
  );
  if (!origin?.secure) return config;
  return {
    ...config,
    ios: { ...config.ios, associatedDomains: [`applinks:${origin.host}`] },
    android: {
      ...config.android,
      intentFilters: [
        {
          action: "VIEW",
          autoVerify: true,
          category: ["BROWSABLE", "DEFAULT"],
          data: [
            { scheme: "https", host: origin.host, pathPrefix: INVITE_PATH },
          ],
        },
      ],
    },
  };
};

export const refuseSelfUpdate = (env: Record<string, string | undefined>) => {
  if (env.EXPO_PUBLIC_DISTRIBUTION === "store" && env.EXPO_PUBLIC_UPDATE_URL)
    throw new Error(
      "EXPO_PUBLIC_UPDATE_URL must not be set for store builds: the stores forbid self-updating apps.",
    );
};

export default ({ config }: ConfigContext): ExpoConfig => {
  refuseSelfUpdate(process.env);
  return withInviteLinks(config as ExpoConfig, process.env);
};
