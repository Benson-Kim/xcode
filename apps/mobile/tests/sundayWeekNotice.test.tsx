import { act, fireEvent, screen, waitFor } from "@testing-library/react-native";

import type { Appearance } from "../src/appearance";
import { catalog, fakeApi, people, tokens } from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

const SINCE = "2026-11-25";
const KEY = "xcode.sunday-week-notice";
const TITLE = /^The week now runs Sunday to Saturday\./;

const stored = (): Map<string, string> => require("expo-secure-store").__items;

function appearanceOn(
  businessDate: string,
  sundayWeekSince: string | null,
): Appearance {
  return {
    organizationName: "Demo Fleet",
    settingsVersion: 4,
    businessDate,
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
      currency: "KES",
      useGrouping: true,
      numberDecimals: 2,
      firstDayOfWeek: 0,
      weekNumbering: "iso8601",
      direction: "ltr",
    },
    themeMode: "system",
    reducedMotion: false,
    fontScale: 1,
    sundayWeekSince,
  };
}

async function signIn(appearance: Appearance) {
  await trustPhone(people.owner, "0733520614");
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  api.on("setup/appearance", [200, appearance]);
  await startApp();
  await typePin("4826");
  await screen.findByText(`Hi ${people.owner.firstName}`);
  // The phone saves the appearance as it applies it; then let the shell take it.
  await waitFor(() =>
    expect(stored().get("xcode.appearance")).toContain("North Star Sacco"),
  );
  await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
  return api;
}

it("tells everyone signed in that the week runs Sunday to Saturday, and remembers the dismissal on this phone", async () => {
  await signIn(appearanceOn("2026-11-27", SINCE));
  expect(await screen.findByText(TITLE)).toBeTruthy();
  expect(
    screen.getByText(
      /Weekly figures from before 25 Nov 2026 were counted Monday to Sunday\.$/,
    ),
  ).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Dismiss" }));
  expect(screen.queryByText(TITLE)).toBeNull();
  await waitFor(() => expect(stored().get(KEY)).toBe(SINCE));
});

it("stays away once this phone dismissed it for that change date", async () => {
  stored().set(KEY, SINCE);
  await signIn(appearanceOn("2026-11-26", SINCE));
  expect(screen.queryByText(TITLE)).toBeNull();
});

it.each([
  ["seven days after the change", "2026-12-02", SINCE],
  ["to an organization that never ran Monday first", "2026-11-26", null],
])("is not shown %s", async (_, businessDate, since) => {
  await signIn(appearanceOn(businessDate, since));
  expect(screen.queryByText(TITLE)).toBeNull();
});
