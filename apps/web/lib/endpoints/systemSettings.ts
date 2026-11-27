import type {
  SystemSettingKey,
  SystemSettings,
} from "@xcode/shared/appearance";

import { apiRequest } from "../data";

export const SYSTEM_SETTINGS_PATH = "setup/settings";

export const systemSettingsApi = {
  switch: (key: SystemSettingKey, on: boolean) =>
    apiRequest<SystemSettings>(`${SYSTEM_SETTINGS_PATH}/${key}`, {
      method: "PUT",
      body: JSON.stringify({ on }),
    }),
};
