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
      if (init?.method === "PUT")
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      if (input.endsWith("organization/settings"))
        return new Response(JSON.stringify(settings), { status: 200 });
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
  expect(
    screen.getByRole("article", { name: "Organization details" }),
  ).toBeInTheDocument();
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
  fireEvent.change(
    screen.getByLabelText("Business date", { selector: "input" }),
    {
      target: { value: "2026-09-20" },
    },
  );
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
  expect(bodies[0]).toEqual({
    value: { name: "New Fleet", slug: "new-fleet" },
  });
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

it("lets a frozen business date move forward to the organization's calendar date", async () => {
  // The business date is held at 15 Mar; the organization's own calendar is at 30 Sep.
  const frozen = {
    ...settings,
    organization: { ...settings.organization, businessDate: "2026-03-15" },
    effectiveBusinessDate: "2026-03-15",
    calendarDate: "2026-09-30",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (_input: string, init?: RequestInit) =>
        new Response(
          JSON.stringify(init?.method === "PUT" ? { ok: true } : frozen),
          { status: 200 },
        ),
    ),
  );
  render(<OrganizationSettingsView />);

  const picker = await screen.findByLabelText("Business date", {
    selector: "input",
  });
  expect(picker).toHaveValue("2026-03-15");
  expect(picker).toHaveAttribute("max", "2026-09-30");
  expect(
    screen.getByText(
      "Held at 15 Mar 2026. The organization's calendar date is 30 Sep 2026.",
    ),
  ).toBeInTheDocument();

  fireEvent.change(picker, { target: { value: "2026-03-16" } });
  fireEvent.click(screen.getByRole("button", { name: "Save business date" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/setup/organization/settings/businessDate",
      expect.objectContaining({
        body: JSON.stringify({ value: "2026-03-16" }),
      }),
    ),
  );
});

// The settings are read again after every save, so values the server works out (the calendar date and the effective
// business date) follow the change instead of staying as they were when the page opened.
function serveSettings(versions: object[]) {
  let reads = 0;
  const fetchMock = vi.fn(async (_input: string, init?: RequestInit) => {
    if (init?.method === "PUT")
      return new Response(JSON.stringify({ section: "saved" }), {
        status: 200,
      });
    const body = versions[Math.min(reads, versions.length - 1)];
    reads += 1;
    return new Response(JSON.stringify(body), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

it("moves the business date's upper limit when a new time zone changes the calendar date", async () => {
  const before = {
    ...settings,
    effectiveBusinessDate: "2026-09-30",
    calendarDate: "2026-09-30",
  };
  const after = {
    ...before,
    localization: { ...settings.localization, timeZone: "Pacific/Kiritimati" },
    effectiveBusinessDate: "2026-10-01",
    calendarDate: "2026-10-01",
  };
  serveSettings([before, after]);
  render(<OrganizationSettingsView />);

  const picker = await screen.findByLabelText("Business date", {
    selector: "input",
  });
  expect(picker).toHaveAttribute("max", "2026-09-30");
  fireEvent.click(screen.getByRole("button", { name: "Save locale" }));

  await waitFor(() =>
    expect(
      screen.getByLabelText("Business date", { selector: "input" }),
    ).toHaveAttribute("max", "2026-10-01"),
  );
  expect(
    screen.getByLabelText("Business date", { selector: "input" }),
  ).toHaveValue("2026-10-01");
  expect(
    screen.getByText("Following the organization's calendar date, 1 Oct 2026."),
  ).toBeInTheDocument();
});

it("shows the calendar date once the held business date is dropped", async () => {
  const held = {
    ...settings,
    organization: { ...settings.organization, businessDate: "2026-03-15" },
    effectiveBusinessDate: "2026-03-15",
    calendarDate: "2026-09-30",
  };
  const following = {
    ...held,
    organization: { ...settings.organization, businessDate: null },
    effectiveBusinessDate: "2026-09-30",
  };
  const fetchMock = serveSettings([held, following]);
  render(<OrganizationSettingsView />);

  expect(
    await screen.findByLabelText("Business date", { selector: "input" }),
  ).toHaveValue("2026-03-15");
  fireEvent.click(
    screen.getByRole("button", { name: "Follow organization time zone" }),
  );
  expect(
    screen.getByLabelText("Business date", { selector: "input" }),
  ).toHaveValue("2026-09-30");
  expect(
    screen.getByText(
      "Following the organization's calendar date, 30 Sep 2026.",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText(/Held at/)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Save business date" }));
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.filter(([, init]) => !init?.method),
    ).toHaveLength(2),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/setup/organization/settings/businessDate",
    expect.objectContaining({ body: JSON.stringify({ value: null }) }),
  );
  expect(
    screen.getByLabelText("Business date", { selector: "input" }),
  ).toHaveValue("2026-09-30");
});

it("keeps the wrong-PIN policy inside the server's bounds: 3 to 10 tries, a pause of 1 to 60 minutes", async () => {
  render(<OrganizationSettingsView />);
  const tries = await screen.findByLabelText("Wrong PINs before a pause");
  const pause = screen.getByLabelText("Pause length in minutes");
  expect(tries).toHaveAttribute("min", "3");
  expect(tries).toHaveAttribute("max", "10");
  expect(pause).toHaveAttribute("min", "1");
  expect(pause).toHaveAttribute("max", "60");
  expect(
    screen.getByText(
      "1 to 60, so a pause lasts at most an hour. A PIN reset by email still lifts a pause.",
    ),
  ).toBeInTheDocument();
  const puts = () =>
    vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "PUT");

  for (const [field, value, message] of [
    [tries, "2", "Wrong PINs before a pause: use 3 to 10."],
    [tries, "11", "Wrong PINs before a pause: use 3 to 10."],
    [pause, "61", "Pause length: use 1 to 60."],
    [pause, "0", "Pause length: use 1 to 60."],
  ] as const) {
    fireEvent.change(tries, { target: { value: "5" } });
    fireEvent.change(pause, { target: { value: "15" } });
    fireEvent.change(field, { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Save security" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(puts()).toHaveLength(0);
  }

  fireEvent.change(tries, { target: { value: "10" } });
  fireEvent.change(pause, { target: { value: "60" } });
  fireEvent.click(screen.getByRole("button", { name: "Save security" }));
  await waitFor(() => expect(puts()).toHaveLength(1));
  expect(JSON.parse(String(puts()[0][1]!.body)).value).toMatchObject({
    lockoutThreshold: 10,
    lockoutMinutes: 60,
  });
});

it("says what the business date is now after following the calendar again", async () => {
  const frozen = {
    ...settings,
    organization: { ...settings.organization, businessDate: "2026-09-29" },
    effectiveBusinessDate: "2026-09-29",
    calendarDate: "2026-09-30",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async (_input: string, init?: RequestInit) =>
        new Response(
          JSON.stringify(init?.method === "PUT" ? { ok: true } : frozen),
          { status: 200 },
        ),
    ),
  );
  render(<OrganizationSettingsView />);
  expect(
    await screen.findByText(
      "Held at 29 Sep 2026. The organization's calendar date is 30 Sep 2026.",
    ),
  ).toBeInTheDocument();

  fireEvent.click(
    screen.getByRole("button", { name: "Follow organization time zone" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save business date" }));
  expect(
    await screen.findByText(
      "Following the organization's calendar date, 30 Sep 2026.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByLabelText("Business date", { selector: "input" }),
  ).toHaveValue("2026-09-30");
});

it("checks the security policy's limits before saving, and caps the pause at an hour", async () => {
  render(<OrganizationSettingsView />);
  await screen.findByDisplayValue("Demo Fleet");
  fireEvent.change(screen.getByLabelText("Wrong PINs before a pause"), {
    target: { value: "2" },
  });
  fireEvent.change(screen.getByLabelText("Pause length in minutes"), {
    target: { value: "90" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save security" }));

  expect(screen.getByRole("alert")).toHaveTextContent(
    "Wrong PINs before a pause: use 3 to 10. Pause length: use 1 to 60.",
  );
  expect(fetch).not.toHaveBeenCalledWith(
    "/api/setup/organization/settings/securityPolicy",
    expect.anything(),
  );
});
