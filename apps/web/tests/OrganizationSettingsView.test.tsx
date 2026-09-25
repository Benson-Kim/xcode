import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { OrganizationSettingsView } from "../components/OrganizationSettingsView";

const settings = {
  organization: { name: "Demo Fleet", slug: "demo-fleet" },
  localization: {
    locale: "en-GB",
    timeZone: "Africa/Nairobi",
    currency: "KES",
    datePattern: "medium",
    hour12: false,
    firstDayOfWeek: 1,
    weekNumbering: "iso8601",
    useGroupping: true,
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

const preferences = {
  locale: "en-GB",
  timeZone: "Africa/Nairobi",
  hour12: false,
  themeMode: "system",
  reducedMotion: false,
  fontScale: 1,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
      if (init?.method === "PUT") return new Response(JSON.stringify({ ok: true }), { status: 200 });
      if (input.endsWith("organization/settings")) return new Response(JSON.stringify(settings), { status: 200 });
      return new Response(JSON.stringify(preferences), { status: 200 });
    }),
  );
});

it("loads organization settings and personal preferences", async () => {
  render(<OrganizationSettingsView />);

  expect(await screen.findByDisplayValue("Demo Fleet")).toBeInTheDocument();
  expect(screen.getByLabelText("Time zone")).toHaveValue("Africa/Nairobi");
  expect(screen.getByRole("combobox", { name: "Theme" })).toHaveValue("system");
  expect(fetch).toHaveBeenCalledWith("/api/setup/organization/settings", expect.anything());
  expect(fetch).toHaveBeenCalledWith("/api/setup/preferences", expect.anything());
});

it("saves organization sections and user preferences through their endpoint contracts", async () => {
  render(<OrganizationSettingsView />);
  await screen.findByDisplayValue("Demo Fleet");

  fireEvent.change(screen.getByLabelText("Locale"), { target: { value: "fr-FR" } });
  fireEvent.click(screen.getByRole("button", { name: "Save locale" }));
  fireEvent.click(screen.getByRole("button", { name: "Save security" }));
  fireEvent.change(screen.getByLabelText("Font scale"), { target: { value: "1.2" } });
  fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));

  await waitFor(() => expect(fetch).toHaveBeenCalledWith(
    "/api/setup/organization/settings/localization",
    expect.objectContaining({ method: "PUT" }),
  ));
  expect(fetch).toHaveBeenCalledWith(
    "/api/setup/organization/settings/securityPolicy",
    expect.objectContaining({ method: "PUT" }),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/setup/preferences",
    expect.objectContaining({ method: "PUT" }),
  );
  expect(await screen.findByRole("status")).toHaveTextContent("Your preferences saved.");
});
