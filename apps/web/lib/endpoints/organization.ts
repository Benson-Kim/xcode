import { apiRequest } from "../data";

export const SETTINGS_PATH = "setup/organization/settings";
export const LOGO_PATH = "setup/organization/logo";
export const PREFERENCES_PATH = "setup/preferences";

export const settingsSectionPath = (section: string) =>
  `${SETTINGS_PATH}/${section}`;

export type SaveSectionRequest = { value: unknown };

export const organizationApi = {
  saveSection: (section: string, value: unknown) =>
    apiRequest(settingsSectionPath(section), {
      method: "PUT",
      body: JSON.stringify({ value } satisfies SaveSectionRequest),
    }),
  saveBusinessDate: (value: string | null) =>
    organizationApi.saveSection("businessDate", value),
  uploadLogo: (dataUrl: string) =>
    apiRequest(LOGO_PATH, {
      method: "PUT",
      body: JSON.stringify({ dataUrl }),
    }),
  removeLogo: () => apiRequest(LOGO_PATH, { method: "DELETE" }),
};

export const preferencesApi = {
  path: PREFERENCES_PATH,
  save: (preferences: object) =>
    apiRequest(PREFERENCES_PATH, {
      method: "PUT",
      body: JSON.stringify(preferences),
    }),
};
