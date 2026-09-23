import { Platform } from "react-native";

import {
  createAuthClient,
  type AuthOperation,
  type AuthRequest,
} from "@xcode/shared";
import { getDeviceId, loadSession } from "./storage";

const baseUrl =
  process.env.EXPO_PUBLIC_API_URL ||
  (Platform.OS === "android"
    ? "http://10.0.2.2:5000"
    : "http://localhost:5000");
const client = createAuthClient(`${baseUrl}/auth`);

export async function authApi(
  operation: AuthOperation | "revoke-device",
  request: AuthRequest = {},
) {
  const deviceId = await getDeviceId();
  const session = await loadSession();

  return client(
    operation === "revoke-device"
      ? `devices/${encodeURIComponent(deviceId)}/revoke`
      : operation,
    { ...request, deviceId, refreshToken: session?.refreshToken || "" },
    session?.accessToken,
  );
}
