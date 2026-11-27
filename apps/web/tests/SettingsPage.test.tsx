import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { OrganizationSettingsView } from "../components/OrganizationSettingsView";
import { SettingsScreen } from "../components/SystemSettings";
import { ToastProvider } from "../components/ui";
import { AppearanceProvider } from "../lib/appearance";
import { SessionProvider } from "../lib/session-context";
import { fakeApi } from "./fakeApi";
import { appearanceFixture, settingsFixture } from "./fixtures";

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on("GET setup/organization/settings", [200, settingsFixture]);
  fake.on("PUT setup/organization/settings/*", [200, { ok: true }]);
  fake.on("GET setup/settings", [
    200,
    { settings: [{ key: "targets", label: "Targets", on: true }] },
  ]);
  fake.on("PUT setup/settings/targets", [
    200,
    { settings: [{ key: "targets", label: "Targets", on: false }] },
  ]);
});

function renderSettings(permissions: string[], refresh = vi.fn()) {
  render(
    <SessionProvider
      value={{
        session: {
          userId: "me",
          firstName: "Test",
          lastName: "User",
          role: "Owner",
          permissions,
        },
        can: (permission) => permissions.includes(permission),
      }}
    >
      <AppearanceProvider
        value={{ appearance: appearanceFixture(), loading: false, refresh }}
      >
        <ToastProvider>
          <SettingsScreen />
        </ToastProvider>
      </AppearanceProvider>
    </SessionProvider>,
  );
  return refresh;
}

const puts = () =>
  fake.calls
    .filter((call) => call.method === "PUT")
    .map((call) => [call.path, call.body]);

it("lists each system setting with its state and switches it at once, then reads the appearance again", async () => {
  const refresh = renderSettings(["settings.edit", "organization.manage"]);

  const row = within(await screen.findByRole("row", { name: /Targets/ }));
  expect(row.getByText("On")).toBeVisible();
  expect(await screen.findByDisplayValue("Demo Fleet")).toBeVisible();
  fireEvent.click(row.getByRole("button", { name: "Switch off Targets" }));

  expect(await screen.findByText("Targets switched off")).toBeVisible();
  expect(puts()).toEqual([["setup/settings/targets", { on: false }]]);
  expect(refresh).toHaveBeenCalledTimes(1);
  const after = within(screen.getByRole("row", { name: /Targets/ }));
  expect(after.getByText("Off")).toBeVisible();
  expect(
    after.getByRole("button", { name: "Switch on Targets" }),
  ).toBeVisible();
});

it("shows the system settings alone to settings.edit without organization.manage", async () => {
  renderSettings(["settings.edit"]);

  expect(screen.getByRole("heading", { name: "Settings" })).toBeVisible();
  expect(
    await screen.findByRole("button", { name: "Switch off Targets" }),
  ).toBeVisible();
  expect(screen.queryByLabelText("Organization name")).not.toBeInTheDocument();
  expect(fake.calls.map((call) => call.path)).not.toContain(
    "setup/organization/settings",
  );
});

it("hides the system settings, and never asks for them, without settings.edit", async () => {
  renderSettings(["organization.manage"]);

  expect(await screen.findByDisplayValue("Demo Fleet")).toBeVisible();
  expect(screen.queryByText("Switch off")).not.toBeInTheDocument();
  expect(fake.calls.map((call) => call.path)).not.toContain("setup/settings");
});

it("saves the fuel question amount in the revenue section, 10,000 until one is set", async () => {
  render(<OrganizationSettingsView />);
  const field = await screen.findByLabelText("Fuel question from, KES");

  expect(field).toHaveValue(10000);
  expect(screen.queryByLabelText(/Low day threshold/)).not.toBeInTheDocument();
  fireEvent.change(field, { target: { value: "0" } });
  fireEvent.click(screen.getByRole("button", { name: "Save revenue" }));
  expect(
    await screen.findByText(
      "Enter the fuel question amount as whole shillings.",
    ),
  ).toBeVisible();
  expect(puts()).toEqual([]);

  fireEvent.change(field, { target: { value: "12000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save revenue" }));
  await waitFor(() => expect(puts()).toHaveLength(1));
  expect(puts()[0]).toEqual([
    "setup/organization/settings/revenue",
    { value: { fuelQuestionFrom: 12000 } },
  ]);
});

it("shows the fuel question amount the organization set", async () => {
  fake.on("GET setup/organization/settings", [
    200,
    { ...settingsFixture, revenue: { fuelQuestionFrom: 15000 } },
  ]);
  render(<OrganizationSettingsView />);

  expect(await screen.findByLabelText("Fuel question from, KES")).toHaveValue(
    15000,
  );
});
