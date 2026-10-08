import type { Appearance } from "../lib/appearance";
import type { Reply } from "./fakeApi";

// The appearance the app shell loads from /setup/appearance, with the organization's business date.
export function appearanceFixture(businessDate?: string): Appearance {
  return {
    organizationName: "Demo Fleet",
    settingsVersion: 1,
    businessDate,
    branding: {
      displayName: "XCODE",
      logoAlt: "XCODE",
      primary: "#1D5FD6",
      secondary: "#14213D",
      accent: "#1E6B3A",
      logo: null,
    },
    formats: {
      locale: "en-GB",
      timeZone: "UTC",
      datePattern: "medium",
      hour12: false,
      currency: "KES",
      useGrouping: true,
      numberDecimals: 2,
      firstDayOfWeek: 1,
      weekNumbering: "iso8601",
      direction: "ltr",
    },
    themeMode: "system",
    reducedMotion: false,
    fontScale: 1,
  };
}

export const settingsFixture = {
  organization: { name: "Demo Fleet", slug: "demo-fleet" },
  localization: {
    locale: "en-GB",
    timeZone: "Africa/Nairobi",
    currency: "KES",
    datePattern: "medium",
    hour12: false,
    firstDayOfWeek: 1,
    weekNumbering: "iso8601",
    useGrouping: true,
    numberDecimals: 2,
    allowLocaleOverride: true,
    allowTimeZoneOverride: false,
    allowHour12Override: true,
    allowThemeOverride: true,
  },
  branding: {
    displayName: "XCODE",
    legalName: "XCODE",
    logoAlt: "XCODE",
    primary: "#1647A6",
    secondary: "#14213D",
    accent: "#1E6B3A",
  },
  securityPolicy: {
    passwordMinLength: 12,
    passwordComplexity: true,
    passwordHistory: 5,
    pinLength: 4,
    lockoutThreshold: 5,
    lockoutMinutes: 15,
    accessTokenMinutes: 10,
    refreshTokenDays: 30,
    idleUnlockSeconds: 300,
    allowPinSignIn: true,
  },
  effective: {},
};

export const preferencesFixture = {
  locale: "en-GB",
  timeZone: "Africa/Nairobi",
  hour12: false,
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
};

export const catalogFixture = [
  {
    name: "Revenue",
    items: [
      { key: "revenue.view", label: "View revenue records", needs: [] },
      {
        key: "revenue.capture",
        label: "Capture revenue",
        needs: ["revenue.view"],
      },
      { key: "reports.view", label: "View reports", needs: [] },
    ],
  },
];

export const rolesFixture = [
  {
    id: "role-1",
    name: "Revenue clerk",
    permissions: ["revenue.view", "revenue.capture"],
  },
  {
    id: "role-2",
    name: "Fleet manager",
    permissions: ["fleet.view", "fleet.manage"],
  },
];

export const scopeOptionsFixture = {
  companies: [{ id: "company-1", name: "North Star" }],
  vehicles: [
    { id: "vehicle-1", registration: "KDA 482M", companyId: "company-1" },
  ],
};

export const personFixture = (over: object = {}) => ({
  id: "person-2",
  firstName: "Grace",
  lastName: "Achieng",
  email: "grace@example.com",
  phoneNumber: "+254711222333",
  role: "Revenue clerk",
  active: true,
  scopeMode: "companies",
  companyIds: ["company-1"],
  vehicleIds: [] as string[],
  permissions: ["revenue.view", "revenue.capture"],
  hasPin: true,
  version: 3,
  ...over,
});

export const peoplePage = (items: object[]) => ({
  items,
  pageNumber: 1,
  pageSize: 25,
  total: items.length,
});

export const problem = (
  status: number,
  title: string,
  detail?: string,
): Reply => [status, { title, status, detail }];
