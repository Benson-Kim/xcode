import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { PreferencesView } from "../components/PreferencesView";
import { renderInApp } from "./renderInApp";

// The organization lets people pick their locale and clock, but not their time zone.
const loaded = {
  locale: null,
  timeZone: null,
  hour12: true,
  themeMode: null,
  reducedMotion: false,
  fontScale: 1,
  allowLocaleOverride: true,
  allowTimeZoneOverride: false,
  allowHour12Override: true,
  allowThemeOverride: true,
  organization: { locale: "en-GB", timeZone: "Africa/Nairobi", hour12: false },
};

let fetcher: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetcher = vi.fn().mockImplementation(
    async (_input: string, init?: RequestInit) =>
      new Response(JSON.stringify(init?.method === "PUT" ? {} : loaded), {
        status: 200,
      }),
  );
  vi.stubGlobal("fetch", fetcher);
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
    expect(fetcher.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(
      true,
    ),
  );
  const [, put] = fetcher.mock.calls.find(
    ([, init]) => init?.method === "PUT",
  )!;
  expect(JSON.parse(String(put.body)).hour12).toBeNull();
});
