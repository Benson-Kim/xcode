import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { OrganizationSettingsView } from "../components/OrganizationSettingsView";
import { PreferencesView } from "../components/PreferencesView";
import { fakeApi } from "./fakeApi";
import { preferencesFixture, problem, settingsFixture } from "./fixtures";
import { renderInApp } from "./renderInApp";

const settings = settingsFixture;

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on("setup/organization/settings", [200, settingsFixture]);
  fake.on("setup/preferences", [200, preferencesFixture]);
  fake.on("PUT setup/organization/settings/*", [200, { ok: true }]);
  fake.on("PUT setup/organization/logo", [200, { ok: true }]);
  fake.on("PUT setup/preferences", [200, { ok: true }]);
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
  fake.on("setup/organization/settings", [200, frozen]);
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
  fake.on("setup/organization/settings", () => {
    const body = versions[Math.min(reads, versions.length - 1)];
    reads += 1;
    return [200, body];
  });
  fake.on("PUT setup/organization/settings/*", [200, { section: "saved" }]);
  return fake.fetch;
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
  fake.on("setup/organization/settings", [200, frozen]);
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

const STALE = "Settings changed. Reload before saving.";
const NOT_PERMITTED =
  "Your access does not include this. Ask your admin if you need it.";
const OFFLINE = "Unable to reach the server. Check your connection.";
const card = (name: string) => within(screen.getByRole("article", { name }));

async function openSettings() {
  renderInApp(<OrganizationSettingsView />);
  await screen.findByDisplayValue("Demo Fleet");
}

function changeName(value: string) {
  const name = screen.getByLabelText("Organization name");
  fireEvent.change(name, { target: { value } });
  return name;
}

const saveOrganization = () =>
  screen.getByRole("button", { name: "Save organization details" });

it("keeps what was typed and says so when the settings changed under the person", async () => {
  fake.on("PUT setup/organization/settings/organization", problem(409, STALE));
  await openSettings();
  const name = changeName("New Fleet");
  fireEvent.click(saveOrganization());

  expect(
    await card("Organization details").findByRole("alert"),
  ).toHaveTextContent(STALE);
  expect(name).toHaveValue("New Fleet");
  expect(saveOrganization()).toBeEnabled();
  expect(
    screen.queryByText("Organization details saved."),
  ).not.toBeInTheDocument();
  expect(fake.sent("setup/organization/settings")).toHaveLength(1);
  expect(
    fake.sent("PUT setup/organization/settings/organization"),
  ).toHaveLength(1);
});

it("says plainly when the server refuses without a reason, and shows the reason when it gives one", async () => {
  fake.on(
    "PUT setup/organization/settings/organization",
    problem(403, "Not permitted in this organization or data scope."),
  );
  await openSettings();
  const name = changeName("New Fleet");
  fireEvent.click(saveOrganization());
  expect(
    await card("Organization details").findByRole("alert"),
  ).toHaveTextContent(NOT_PERMITTED);
  expect(name).toHaveValue("New Fleet");
  expect(saveOrganization()).toBeEnabled();
  expect(
    screen.queryByText("Organization details saved."),
  ).not.toBeInTheDocument();

  const why = "Only an owner can rename the organization.";
  fake.on(
    "PUT setup/organization/settings/organization",
    problem(403, "Not permitted in this organization or data scope.", why),
  );
  fireEvent.click(saveOrganization());
  expect(await screen.findByText(why)).toBeInTheDocument();
  expect(
    screen.queryByText("Not permitted in this organization or data scope."),
  ).not.toBeInTheDocument();
  expect(name).toHaveValue("New Fleet");
});

it("keeps the typed locale when offline, and saves once the connection is back", async () => {
  fake.on("PUT setup/organization/settings/localization", "offline");
  await openSettings();
  const locale = screen.getByLabelText("Locale");
  fireEvent.change(locale, { target: { value: "fr-FR" } });
  fireEvent.click(screen.getByRole("button", { name: "Save locale" }));

  expect(await card("Locale and time").findByRole("alert")).toHaveTextContent(
    OFFLINE,
  );
  expect(locale).toHaveValue("fr-FR");
  expect(screen.getByRole("button", { name: "Save locale" })).toBeEnabled();
  expect(screen.queryByText("Locale and time saved.")).not.toBeInTheDocument();
  expect(fake.sent("setup/organization/settings")).toHaveLength(1);

  fake.on("PUT setup/organization/settings/localization", [200, {}]);
  fireEvent.click(screen.getByRole("button", { name: "Save locale" }));
  expect(await screen.findByText("Locale and time saved.")).toBeInTheDocument();
  expect(card("Locale and time").queryByRole("alert")).not.toBeInTheDocument();
  expect(
    fake.sent("PUT setup/organization/settings/localization"),
  ).toHaveLength(2);
});

it("shows a proxy outage inside the business date card only", async () => {
  fake.on("PUT setup/organization/settings/businessDate", [
    503,
    { status: "service_unavailable", requestId: "r1" },
  ]);
  await openSettings();
  const date = screen.getByLabelText("Business date", { selector: "input" });
  fireEvent.change(date, { target: { value: "2026-09-20" } });
  fireEvent.click(screen.getByRole("button", { name: "Save business date" }));

  expect(await card("Business date").findByRole("alert")).toHaveTextContent(
    "The request could not be completed.",
  );
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(date).toHaveValue("2026-09-20");
  expect(
    screen.getByRole("button", { name: "Save business date" }),
  ).toBeEnabled();
  expect(screen.queryByText("Business date saved.")).not.toBeInTheDocument();
  expect(fake.sent("setup/organization/settings")).toHaveLength(1);
});

it("keeps the current logo when the upload is refused", async () => {
  fake.on("PUT setup/organization/logo", problem(409, STALE));
  await openSettings();
  const input = screen.getByText("Upload logo").querySelector("input")!;
  fireEvent.change(input, {
    target: {
      files: [
        new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "logo.png", {
          type: "image/png",
        }),
      ],
    },
  });

  expect(await card("Brand").findByRole("alert")).toHaveTextContent(STALE);
  expect(screen.queryByText("Logo updated.")).not.toBeInTheDocument();
  expect(screen.getByText("Upload logo")).toBeInTheDocument();
  expect(fake.sent("setup/organization/settings")).toHaveLength(1);
});

it("loads after a passing outage", async () => {
  fake.once("setup/organization/settings", [503, {}]);
  renderInApp(<OrganizationSettingsView />);
  expect(
    await screen.findByDisplayValue("Demo Fleet", {}, { timeout: 3000 }),
  ).toBeInTheDocument();
  expect(fake.sent("setup/organization/settings")).toHaveLength(2);
});

it("says the server cannot be reached when the load keeps failing", async () => {
  fake.on("setup/organization/settings", "offline");
  renderInApp(<OrganizationSettingsView />);
  expect(
    await screen.findByText(OFFLINE, {}, { timeout: 6000 }),
  ).toBeInTheDocument();
}, 10000);
