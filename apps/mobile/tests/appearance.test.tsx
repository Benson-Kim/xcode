import { fireEvent, screen } from "@testing-library/react-native";

import { resolveTheme } from "@xcode/shared/appearance";
import { createFormatter, type Formats } from "@xcode/shared/format";

import {
  loadSavedAppearance,
  themeFor,
  type Appearance,
} from "../src/appearance";
import { periodLabel } from "../src/shell/access";
import { darkPalette, mix, palette } from "../src/ui";
import { catalog, fakeApi, people, revenueDashboard, tokens } from "./fakeApi";
import { startApp, storedText, trustPhone, typePin } from "./helpers";

const appearance: Appearance = {
  organizationName: "Demo Fleet",
  settingsVersion: 4,
  branding: {
    displayName: "North Star Sacco",
    logoAlt: "North Star",
    primary: "#0B7A75",
    secondary: "#3B1F5C",
    accent: "#1E6B3A",
    logo: null,
  },
  formats: {
    locale: "en-GB",
    timeZone: "Africa/Nairobi",
    datePattern: "medium",
    hour12: false,
    currency: "USD",
    useGrouping: true,
    numberDecimals: 2,
    firstDayOfWeek: 1,
    weekNumbering: "iso8601",
    direction: "ltr",
  },
  themeMode: "system",
  reducedMotion: true,
  fontScale: 1.25,
};

it("mixes the organization's colours into the theme as XCODE Web does", () => {
  const theme = themeFor(appearance);
  expect(theme.colors.blue).toBe("#0B7A75");
  expect(theme.colors.blueDark).toBe("#09625E");
  expect(theme.colors.brand).toBe("#3B1F5C");
  expect(theme.reducedMotion).toBe(true);
  expect(theme.fontScale).toBe(1.25);
  // An invalid colour keeps the design's.
  expect(
    themeFor({
      ...appearance,
      branding: { ...appearance.branding, primary: "teal" },
    }).colors.blue,
  ).toBe("#1D5FD6");
});

it("reads the organization's colours against a dark surface when the theme asks for one", () => {
  // "system" follows the phone. An organization that locks the theme is sent "light", so the phone is not consulted.
  expect(resolveTheme("system", true)).toBe("dark");
  expect(resolveTheme("light", true)).toBe("light");
  expect(resolveTheme("dark", false)).toBe("dark");
  expect(themeFor(appearance, true).dark).toBe(true);
  expect(themeFor(appearance, false).dark).toBe(false);

  const dark = themeFor({ ...appearance, themeMode: "dark" }, false);
  // The page, the ink and the surface a card sits on all swap over.
  expect(dark.colors.cream).toBe(darkPalette.cream);
  expect(dark.colors.navy).toBe(darkPalette.navy);
  expect(dark.colors.surface).toBe(darkPalette.surface);
  // The organization's primary is lightened, because the ink on a filled button goes dark here...
  expect(dark.colors.blue).toBe(mix("#0B7A75", 60, "#FFFFFF"));
  expect(dark.colors.onFill).toBe(darkPalette.onFill);
  // ...while the ink on the brand colour stays white, because that fill stays dark in both themes.
  expect(dark.colors.brand).toBe("#3B1F5C");
  expect(dark.colors.onBrand).toBe("#FFFFFF");
  // A tint is mixed towards the surface it will sit on rather than towards white.
  expect(dark.colors.blueTint).toBe(mix("#0B7A75", 18, darkPalette.field));
  // Every colour the app asks for exists in both palettes, so no screen can fall back to a light one.
  expect(Object.keys(dark.colors).sort()).toEqual(Object.keys(palette).sort());
  // Before the first appearance arrives - the unlock screen offline - the phone's own setting still decides.
  expect(themeFor(null, true).colors.cream).toBe(darkPalette.cream);
  expect(themeFor(null, false).colors.cream).toBe(palette.cream);
});

it("formats money in the organization's currency", () => {
  expect(createFormatter({ currency: "USD" }).kes(1200)).toBe("USD 1,200");
  expect(createFormatter(null).kes(49000.5)).toBe("KES 49,000.50");
});

it("applies saved settings at sign in and keeps them for the next unlock", async () => {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/appearance", [200, appearance]);
  api.on("setup/revenue/dashboard?period=month", [
    200,
    { ...revenueDashboard, period: "month" },
  ]);
  await startApp();
  await screen.findByText("XCODE");
  await typePin("4826");

  // Revenue in the organization's currency; Net contribution and Money out say they are not connected rather than show zeros.
  expect(await screen.findByText("USD 0")).toBeTruthy();
  expect(
    screen.getByText(
      "0% of target USD 2,000, from each vehicle’s weekly target",
    ),
  ).toBeTruthy();
  expect(screen.getAllByText("Not available yet")).toHaveLength(2);
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

it("still unlocks with an appearance cached by an older version of the app", async () => {
  await trustPhone(people.owner, "0733520614");
  const store = require("expo-secure-store");
  const { weekNumbering, direction, ...formats } = appearance.formats;
  const { lockoutThreshold, lockoutMinutes, ...legacy } = appearance;
  expect([weekNumbering, direction, lockoutThreshold, lockoutMinutes]).toEqual([
    "iso8601",
    "ltr",
    undefined,
    undefined,
  ]);
  await store.setItemAsync(
    "xcode.appearance",
    JSON.stringify({ ...legacy, formats, themeMode: "midnight" }),
  );
  fakeApi().on("auth/unlock", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  expect(screen.getByText("North Star Sacco")).toBeTruthy();
  expect(
    themeFor(
      { ...legacy, formats, themeMode: "midnight" } as unknown as Appearance,
      true,
    ).dark,
  ).toBe(true);
  expect(
    themeFor(
      { ...legacy, formats, themeMode: "midnight" } as unknown as Appearance,
      false,
    ).dark,
  ).toBe(false);
});

it("names this week from the organization's first day of the week, Monday until it is known", () => {
  const formatterFor = (formats: Partial<Formats> | null) =>
    createFormatter(formats);
  // Wednesday 30 Sep 2026.
  expect(periodLabel(formatterFor(null), "week", "2026-09-30")).toBe(
    "This week, 28 Sep to 4 Oct 2026",
  );
  expect(
    periodLabel(formatterFor({ firstDayOfWeek: 0 }), "week", "2026-09-30"),
  ).toBe("This week, 27 Sep to 3 Oct 2026");
  expect(
    periodLabel(formatterFor({ firstDayOfWeek: 6 }), "week", "2026-10-03"),
  ).toBe("This week, 3 to 9 Oct 2026");
  // Out of range: the API's default, Monday.
  expect(
    periodLabel(formatterFor({ firstDayOfWeek: 9 }), "week", "2026-09-30"),
  ).toBe("This week, 28 Sep to 4 Oct 2026");
});

it("writes the period labels in the organization's date pattern", () => {
  const short = createFormatter({
    ...appearance.formats,
    datePattern: "short",
  });
  expect(periodLabel(short, "today", "2026-09-30")).toBe("Today, 30/09/2026");
  expect(periodLabel(short, "week", "2026-09-30")).toBe(
    "This week, 28/09/2026 to 04/10/2026",
  );
  expect(periodLabel(short, "month", "2026-09-30")).toBe(
    "This month, 01/09/2026 to 30/09/2026",
  );
});

it("labels the dashboard week as the API counts it for an organization whose week starts on Sunday", async () => {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/appearance", [
    200,
    {
      ...appearance,
      businessDate: "2026-09-30",
      formats: { ...appearance.formats, firstDayOfWeek: 0 },
    },
  ]);
  api.on("setup/revenue/dashboard?period=month", [
    200,
    { ...revenueDashboard, period: "month" },
  ]);
  api.on("setup/revenue/dashboard?period=week", [
    200,
    { ...revenueDashboard, from: "2026-09-27", through: "2026-09-30" },
  ]);
  await startApp();
  await screen.findByText("XCODE");
  await typePin("4826");
  await fireEvent.press(
    await screen.findByRole("button", { name: "This week" }),
  );
  // The Revenue card covers the week the API counted: Sunday 27 Sep to Saturday 3 Oct.
  expect(
    await screen.findAllByText("This week, 27 Sep to 3 Oct 2026"),
  ).not.toHaveLength(0);
});

const oldGroupingKey = () => {
  const formats: Record<string, unknown> = { ...appearance.formats };
  delete formats.useGrouping;
  return {
    ...appearance,
    formats: { ...formats, useGroupping: false, numberDecimals: 0 },
  };
};

async function signInWithAppearance(served: unknown) {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/unlock", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/appearance", [200, served]);
  api.on("setup/revenue/dashboard?period=month", [
    200,
    { ...revenueDashboard, period: "month" },
  ]);
  await startApp();
  await screen.findByText("XCODE");
  await typePin("4826");
  await screen.findByText("USD 0");
}

it("reads an appearance cached with the old digit grouping key", async () => {
  const store = require("expo-secure-store");
  await store.setItemAsync(
    "xcode.appearance",
    JSON.stringify(oldGroupingKey()),
  );
  const saved = await loadSavedAppearance();
  expect(saved?.formats.useGrouping).toBe(false);
  expect("useGroupping" in saved!.formats).toBe(false);
  expect(createFormatter(saved!.formats).kes(12345)).toBe("USD 12345");
});

it("still unlocks offline from a cache that has the old digit grouping key", async () => {
  await trustPhone(people.owner, "0733520614");
  const store = require("expo-secure-store");
  await store.setItemAsync(
    "xcode.appearance",
    JSON.stringify(oldGroupingKey()),
  );
  fakeApi().on("auth/unlock", "offline");
  await startApp();
  await screen.findByText("Welcome back, Antony");
  expect(screen.getByText("North Star Sacco")).toBeTruthy();
});

it("stores the new digit grouping key after an online sign in", async () => {
  await signInWithAppearance(oldGroupingKey());
  expect(storedText()).toContain('"useGrouping":false');
  expect(storedText()).not.toContain("useGroupping");
});

it("accepts both digit grouping keys during the transition", async () => {
  const both = {
    ...oldGroupingKey(),
    formats: {
      ...oldGroupingKey().formats,
      useGroupping: true,
      useGrouping: false,
    },
  };
  await signInWithAppearance(both);
  expect(storedText()).toContain('"useGrouping":false');
  expect(storedText()).not.toContain("useGroupping");
});
