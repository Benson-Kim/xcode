import { screen } from "@testing-library/react-native";
import { themeFor, type Appearance } from "../src/appearance";
import { configureFormats, money } from "../src/lib/format";
import { catalog, fakeApi, people, revenueDashboard, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

const appearance: Appearance = {
  organizationName: "Demo Fleet",
  settingsVersion: 4,
  branding: { displayName: "North Star Sacco", logoAlt: "North Star", primary: "#0B7A75", secondary: "#3B1F5C", accent: "#1E6B3A", logo: null },
  formats: { locale: "en-GB", timeZone: "Africa/Nairobi", datePattern: "medium", hour12: false, currency: "USD", useGroupping: true, numberDecimals: 2 },
  themeMode: "system",
  reducedMotion: true,
  fontScale: 1.25,
};

afterEach(() => configureFormats(null));

it("mixes the organization's colours into the theme as XCODE Web does", () => {
  const theme = themeFor(appearance);
  expect(theme.colors.blue).toBe("#0B7A75");
  expect(theme.colors.blueDark).toBe("#09625E");
  expect(theme.colors.brand).toBe("#3B1F5C");
  expect(theme.reducedMotion).toBe(true);
  expect(theme.fontScale).toBe(1.25);
  // An invalid colour keeps the design's.
  expect(themeFor({ ...appearance, branding: { ...appearance.branding, primary: "teal" } }).colors.blue).toBe("#1D5FD6");
});

it("formats money in the organization's currency", () => {
  configureFormats({ currency: "USD" });
  expect(money(1200)).toBe("USD 1,200");
  configureFormats(null);
  expect(money(49000.5)).toBe("KES 49,000.5");
});

it("applies saved settings at sign in and keeps them for the next unlock", async () => {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/appearance", [200, appearance]);
  api.on("setup/revenue/dashboard?period=month", [200, { ...revenueDashboard, period: "month" }]);
  await startApp();
  await screen.findByText("XCODE");
  await typePin("4826");

  // Revenue, Net contribution and Costs, in the organization's currency.
  expect(await screen.findAllByText("USD 0")).toHaveLength(3);
  expect(storedText()).toContain("North Star Sacco");
});

it("shows the organization's brand on the unlock screen, even before going online", async () => {
  await trustPhone(people.owner, "0733520614");
  const store = require("expo-secure-store");
  await store.setItemAsync("xcode.appearance", JSON.stringify(appearance));
  fakeApi().on("auth/unlock", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  expect(screen.getByText("North Star Sacco")).toBeTruthy();
  expect(screen.getByText("Demo Fleet")).toBeTruthy();
});
