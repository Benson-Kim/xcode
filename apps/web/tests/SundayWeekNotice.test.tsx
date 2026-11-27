import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { AppShell } from "../components/AppShell";
import { SUNDAY_WEEK_DISMISSED_KEY } from "../components/SundayWeekNotice";
import { appearanceFixture } from "./renderInApp";

const SINCE = "2026-11-25";

function signIn(businessDate: string, sundayWeekSince: string | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      if (input.includes("/auth/session"))
        return new Response(
          JSON.stringify({
            userId: "me",
            firstName: "Test",
            lastName: "User",
            role: "Clerk",
            permissions: [],
          }),
          { status: 200 },
        );
      if (input.includes("appearance"))
        return new Response(
          JSON.stringify({
            ...appearanceFixture(businessDate),
            sundayWeekSince,
          }),
          { status: 200 },
        );
      return new Response(
        JSON.stringify({ items: [], pageNumber: 1, pageSize: 100, total: 0 }),
        { status: 200 },
      );
    }),
  );
  return render(<AppShell onSignOut={() => {}} />);
}

// The organization's name shows under the brand once the appearance has loaded.
const appearanceLoaded = () => screen.findAllByText("Demo Fleet");

const notice = () =>
  screen.queryByText("The week now runs Sunday to Saturday.");

afterEach(() => window.localStorage.clear());

it("tells everyone signed in that the week runs Sunday to Saturday, and since when", async () => {
  signIn("2026-11-27", SINCE);
  expect(
    await screen.findByText("The week now runs Sunday to Saturday."),
  ).toBeInTheDocument();
  expect(notice()?.closest("[role=status]")).toHaveTextContent(
    "Weekly figures from before 25 Nov 2026 were counted Monday to Sunday.",
  );
});

it("remembers on this browser that it was dismissed", async () => {
  const first = signIn(SINCE, SINCE);
  await screen.findByText("The week now runs Sunday to Saturday.");
  fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(notice()).not.toBeInTheDocument();
  expect(window.localStorage.getItem(SUNDAY_WEEK_DISMISSED_KEY)).toBe(SINCE);
  first.unmount();

  signIn("2026-11-26", SINCE);
  await appearanceLoaded();
  expect(notice()).not.toBeInTheDocument();
});

it.each([
  ["seven days after the change", "2026-12-02", SINCE],
  ["an organization that never ran Monday first", "2026-11-26", null],
])("is not shown %s", async (_, businessDate, since) => {
  signIn(businessDate, since);
  await appearanceLoaded();
  expect(notice()).not.toBeInTheDocument();
});
