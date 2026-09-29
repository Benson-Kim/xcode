import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { OrganizationSettingsView } from "../components/OrganizationSettingsView";
import { PreferencesView } from "../components/PreferencesView";
import { renderInApp } from "./renderInApp";

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

it("loads organization settings without personal preferences", async () => {
  render(<OrganizationSettingsView />);

  expect(await screen.findByDisplayValue("Demo Fleet")).toBeInTheDocument();
  expect(screen.getByLabelText("Organization name")).not.toHaveAttribute(
    "readonly",
  );
  expect(screen.getByRole("article", { name: "Organization details" })).toBeInTheDocument();
  expect(screen.getByLabelText("Time zone")).toHaveValue("Africa/Nairobi");
  expect(screen.queryByLabelText("Font scale")).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "/api/setup/organization/settings",
    expect.anything(),
  );
  expect(fetch).not.toHaveBeenCalledWith(
    "/api/setup/preferences",
    expect.anything(),
  );
});

it("saves organization sections through their endpoint contracts", async () => {
  render(<OrganizationSettingsView />);
  await screen.findByDisplayValue("Demo Fleet");

  fireEvent.change(screen.getByLabelText("Organization name"), {
    target: { value: "New Fleet" },
  });
  fireEvent.change(screen.getByLabelText("Slug"), {
    target: { value: "new-fleet" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Save organization details" }),
  );
  fireEvent.change(screen.getByLabelText("Locale"), {
    target: { value: "fr-FR" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save locale" }));
  fireEvent.click(screen.getByRole("button", { name: "Save security" }));

  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/setup/organization/settings/organization",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/setup/organization/settings/localization",
    expect.objectContaining({ method: "PUT" }),
  );
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/setup/organization/settings/securityPolicy",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
  fireEvent.change(screen.getByLabelText("Business date", { selector: "input" }), {
    target: { value: "2026-09-20" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save business date" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/setup/organization/settings/businessDate",
      expect.objectContaining({ method: "PUT" }),
    ),
  );

  // C7: settings are saved without a typed reason; the server writes one for the change log.
  expect(screen.queryByLabelText(/Reason/)).not.toBeInTheDocument();
  const bodies = vi
    .mocked(fetch)
    .mock.calls.filter(([, init]) => init?.method === "PUT")
    .map(([, init]) => JSON.parse(String(init!.body)));
  expect(bodies).toHaveLength(4);
  for (const body of bodies) expect(body).not.toHaveProperty("reason");
  expect(bodies[0]).toEqual({ value: { name: "New Fleet", slug: "new-fleet" } });
  expect(bodies[3]).toEqual({ value: "2026-09-20" });
});

it("lets any member load and save their own preferences", async () => {
  renderInApp(<PreferencesView />);

  expect(await screen.findByRole("combobox", { name: "Theme" })).toHaveValue(
    "system",
  );
  fireEvent.change(screen.getByLabelText("Font scale"), {
    target: { value: "1.2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));

  expect(await screen.findByRole("status")).toHaveTextContent(
    "Your preferences saved.",
  );
  const put = vi
    .mocked(fetch)
    .mock.calls.find(([, init]) => init?.method === "PUT")!;
  expect(put[0]).toBe("/api/setup/preferences");
  expect(JSON.parse(String(put[1]!.body))).toMatchObject({ fontScale: 1.2 });
  expect(fetch).not.toHaveBeenCalledWith(
    "/api/setup/organization/settings",
    expect.anything(),
  );
});
