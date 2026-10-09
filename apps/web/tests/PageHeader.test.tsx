import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { AppShell } from "../components/AppShell";
import { PageHeader, PageHeaderSlotProvider } from "../components/ui";
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

it("draws the title and description in the slot instead, the title cut short and the description hidden on narrow screens", () => {
  const slot = document.createElement("div");
  document.body.append(slot);
  render(
    <PageHeaderSlotProvider value={slot}>
      <main>
        <PageHeader title="Central expenses" description="All sources" />
      </main>
    </PageHeaderSlotProvider>,
  );
  const heading = screen.getByRole("heading", {
    name: "Central expenses",
    level: 1,
  });
  expect(slot).toContainElement(heading);
  expect(screen.getByRole("main")).not.toContainElement(heading);
  expect(heading.className).toContain("truncate");
  const description = screen.getByText("All sources");
  expect(slot).toContainElement(description);
  expect(description.className).toContain("max-[899px]:hidden");
  expect(description.className).toContain("truncate");
  slot.remove();
});

it("leaves the description out when there is none", () => {
  const slot = document.createElement("div");
  document.body.append(slot);
  render(
    <PageHeaderSlotProvider value={slot}>
      <PageHeader title="Reports" />
    </PageHeaderSlotProvider>,
  );
  expect(slot.querySelector("p")).toBeNull();
  slot.remove();
});

it("shows every page's title in the app shell's top bar, between the brand and the profile button", async () => {
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
  const heading = await screen.findByRole("heading", {
    name: "Reports",
    level: 1,
  });
  const bar = heading.closest("header.sticky")!;
  expect(bar).not.toBeNull();
  expect(screen.getByRole("main")).not.toContainElement(heading);
  const profile = within(bar as HTMLElement).getByRole("button", {
    name: /Test User/,
  });
  expect(
    heading.compareDocumentPosition(profile) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(document.querySelectorAll("h1")).toHaveLength(1);

  // The title starts at the left edge of the page content: a left zone as wide as the menu, then the same inset.
  const zone = heading.closest("header")!.parentElement!;
  const main = screen.getByRole("main");
  const inset = (element: HTMLElement) =>
    element.className
      .split(/\s+/)
      .filter((name) => /^(max-\[899px\]:)?px-\d+$/.test(name))
      .sort();
  expect(inset(zone)).toEqual(["max-[899px]:px-4", "px-8"]);
  expect(inset(main)).toEqual(inset(zone));
  const sideMenu = screen.getByRole("navigation", { name: "Main" });
  const left = bar.firstElementChild as HTMLElement;
  expect(zone.previousElementSibling).toBe(left);
  expect(sideMenu.className).toContain("w-62");
  expect(left.className).toContain("w-62");
  expect(left.className).toContain("max-[899px]:w-auto");
  expect(left).toContainElement(
    within(left).getByRole("button", { name: "Open menu", hidden: true }),
  );
});
