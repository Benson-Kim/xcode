import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { AppShell } from "../components/AppShell";
import { HeroSlotsProvider, PageHeader } from "../components/ui";
import { fakeApi } from "./fakeApi";
import { appearanceFixture } from "./renderInApp";

it("keeps the title inline when the page has no slot to draw it in", () => {
  render(
    <main>
      <PageHeader title="Revenue" description="Per vehicle" />
    </main>,
  );
  const heading = screen.getByRole("heading", { name: "Revenue", level: 1 });
  expect(screen.getByRole("main")).toContainElement(heading);
  expect(screen.getByText("Per vehicle")).toBeInTheDocument();
});

it("draws the title, description and actions in the brand zone instead of the page", () => {
  const title = document.createElement("div");
  const actions = document.createElement("div");
  document.body.append(title, actions);
  render(
    <HeroSlotsProvider value={{ title, actions, band: null }}>
      <main>
        <PageHeader
          title="Central expenses"
          description="All sources"
          actions={<button type="button">Record expense</button>}
        />
      </main>
    </HeroSlotsProvider>,
  );
  const heading = screen.getByRole("heading", {
    name: "Central expenses",
    level: 1,
  });
  expect(title).toContainElement(heading);
  expect(screen.getByRole("main")).not.toContainElement(heading);
  expect(title).toContainElement(screen.getByText("All sources"));
  expect(actions).toContainElement(
    screen.getByRole("button", { name: "Record expense" }),
  );
  title.remove();
  actions.remove();
});

it("leaves the description out when there is none", () => {
  const title = document.createElement("div");
  document.body.append(title);
  render(
    <HeroSlotsProvider value={{ title, actions: null, band: null }}>
      <PageHeader title="Reports" />
    </HeroSlotsProvider>,
  );
  expect(title.querySelector("p")).toBeNull();
  title.remove();
});

it("shows every page's title in the brand zone above the sheet, before the profile button", async () => {
  const api = fakeApi();
  api.on("auth/session", [
    200,
    {
      userId: "me",
      firstName: "Test",
      lastName: "User",
      role: "Clerk",
      permissions: ["reports.view"],
    },
  ]);
  api.on("setup/appearance", [200, appearanceFixture("2026-10-09")]);
  api.on("setup/reports", [
    200,
    {
      businessDate: "2026-10-09",
      firstDayOfWeek: 1,
      fleet: [],
      pettyCash: [],
      holders: [],
      canExport: false,
    },
  ]);
  render(<AppShell onSignOut={() => {}} />);
  const menu = within(await screen.findByRole("navigation", { name: "Main" }));
  fireEvent.click(await menu.findByRole("button", { name: "Reports" }));
  // The screen's code loads on first use.
  const heading = await screen.findByRole(
    "heading",
    { name: "Reports", level: 1 },
    { timeout: 8000 },
  );
  const head = heading.closest(".head") as HTMLElement;
  expect(head).not.toBeNull();
  expect(head.closest(".hero")).not.toBeNull();
  expect(document.querySelector(".pagebody")).not.toContainElement(heading);
  const profile = within(head).getByRole("button", { name: /Test User/ });
  expect(
    heading.compareDocumentPosition(profile) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(document.querySelectorAll("h1")).toHaveLength(1);
  expect(
    within(head).getByRole("button", { name: "Open menu", hidden: true }),
  ).toBeInTheDocument();
});
