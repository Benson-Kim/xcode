import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { PreferencesView } from "../components/PreferencesView";
import { fakeApi } from "./fakeApi";
import { preferencesFixture, problem } from "./fixtures";
import { renderInApp } from "./renderInApp";

// The organization lets people pick their locale and clock, but not their time zone.
const loaded = {
  ...preferencesFixture,
  locale: null,
  timeZone: null,
  hour12: true,
  themeMode: null,
  allowLocaleOverride: true,
  allowTimeZoneOverride: false,
  allowHour12Override: true,
  allowThemeOverride: true,
  organization: { locale: "en-GB", timeZone: "Africa/Nairobi", hour12: false },
};

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on("setup/preferences", [200, loaded]);
  fake.on("PUT setup/preferences", [200, {}]);
});

it("offers only the overrides the organization allows", async () => {
  renderInApp(<PreferencesView />);
  const zone = await screen.findByLabelText("Time-zone override");
  expect(zone).toBeDisabled();
  expect(zone).toHaveValue("Africa/Nairobi");
  expect(
    screen.getByText("Your organization sets this for everyone."),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Locale override")).toBeEnabled();
});

it("hands the clock back to the organization default", async () => {
  renderInApp(<PreferencesView />);
  const clock = await screen.findByLabelText("Clock");
  expect(clock).toHaveValue("12");
  expect(
    screen.getByRole("option", { name: "Organization default (24-hour)" }),
  ).toBeInTheDocument();
  fireEvent.change(clock, { target: { value: "default" } });
  fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
  await waitFor(() =>
    expect(fake.sent("PUT setup/preferences")).toHaveLength(1),
  );
  expect(fake.sent("PUT setup/preferences")[0].hour12).toBeNull();
});

it.each([
  [
    "a passing outage at the proxy",
    [503, { status: "service_unavailable", requestId: "r1" }],
    "The request could not be completed.",
  ],
  [
    "no connection",
    "offline",
    "Unable to reach the server. Check your connection.",
  ],
  [
    "a change made elsewhere",
    problem(409, "Settings changed. Reload before saving."),
    "Settings changed. Reload before saving.",
  ],
  [
    "a refusal with no reason",
    problem(403, "Not permitted in this organization or data scope."),
    "Your access does not include this. Ask your admin if you need it.",
  ],
] as const)(
  "keeps the typed font scale when the save fails with %s, and lets the person try again",
  async (_name, reply, message) => {
    fake.on("PUT setup/preferences", reply);
    renderInApp(<PreferencesView />);
    const scale = await screen.findByLabelText("Font scale");
    fireEvent.change(scale, { target: { value: "1.2" } });
    const save = screen.getByRole("button", { name: "Save preferences" });
    fireEvent.click(save);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(scale).toHaveValue(1.2);
    expect(save).toBeEnabled();
    expect(
      screen.queryByText("Your preferences saved."),
    ).not.toBeInTheDocument();
    expect(fake.sent("PUT setup/preferences")).toHaveLength(1);
    expect(fake.sent("setup/preferences")).toHaveLength(1);

    fake.on("PUT setup/preferences", [200, {}]);
    fireEvent.click(save);
    expect(
      await screen.findByText("Your preferences saved."),
    ).toBeInTheDocument();
    expect(fake.sent("PUT setup/preferences")).toHaveLength(2);
    expect(fake.sent("PUT setup/preferences")[1]).toMatchObject({
      fontScale: 1.2,
    });
  },
);
