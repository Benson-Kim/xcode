import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AppShell } from "../components/AppShell";
import { appearanceFixture } from "./renderInApp";

// The change log's code fails to download twice, first as Turbopack reports it and then as a browser's import() does,
// then arrives. (A getter, because Vitest wraps whatever a mock factory throws; each attempt to load reads it once.)
// The companies page can be made to fail while it renders: a bug, not a download.
const download = vi.hoisted(() => ({
  failures: [
    Object.assign(new Error("Failed to load chunk static/chunks/3fh_3jnvfo2n3.js from module 51570"), { name: "ChunkLoadError" }),
    new TypeError("Failed to fetch dynamically imported module"),
  ],
  attempts: 0,
}));
const crash = vi.hoisted(() => ({ error: new Error("Cannot read properties of undefined (reading 'name')"), on: false }));
vi.mock("../components/setup/HistoryPage", async (importOriginal) => {
  const { HistoryPage } = await importOriginal<typeof import("../components/setup/HistoryPage")>();
  return {
    get HistoryPage() {
      download.attempts++;
      const failure = download.failures.shift();
      if (failure) throw failure;
      return HistoryPage;
    },
  };
});
vi.mock("../components/setup/CompaniesPage", async (importOriginal) => {
  const { CompaniesPage } = await importOriginal<typeof import("../components/setup/CompaniesPage")>();
  return {
    CompaniesPage: () => {
      if (crash.on) throw crash.error;
      return <CompaniesPage />;
    },
  };
});

const loadProblem = "This page could not be loaded. Check your connection and try again.";

function signIn() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      if (input.includes("/auth/session"))
        return new Response(JSON.stringify({ userId: "me", firstName: "Test", lastName: "User", role: "Clerk", permissions: ["audit.view", "companies.manage"] }), { status: 200 });
      if (input.includes("appearance")) return new Response(JSON.stringify(appearanceFixture("2026-09-21")), { status: 200 });
      return new Response(JSON.stringify({ items: [], pageNumber: 1, pageSize: 100, total: 0 }), { status: 200 });
    }),
  );
  render(<AppShell onSignOut={() => {}} />);
  return within(screen.getByRole("navigation", { name: "Main" }));
}

it("keeps a page that could not load inside the app, with the menu working, and loads it on Try again", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const menu = signIn();

  fireEvent.click(await menu.findByRole("button", { name: "Change log" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(loadProblem);
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reload the app" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open menu" })).toBeInTheDocument();

  // The menu still works while the problem shows.
  fireEvent.click(menu.getByRole("button", { name: "PSV companies" }));
  expect(await screen.findByRole("heading", { name: "PSV companies", level: 1 })).toBeInTheDocument();
  expect(screen.queryByText(loadProblem)).not.toBeInTheDocument();

  // Opening it again downloads it again. Offline, reloading would lose the app, so only Try again is offered.
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  fireEvent.click(menu.getByRole("button", { name: "Change log" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(loadProblem);
  expect(download.attempts).toBe(2);
  expect(screen.queryByRole("button", { name: "Reload the app" })).not.toBeInTheDocument();

  // Try again: focus goes to the placeholder while the page loads, then to its heading.
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(screen.getByRole("status")).toHaveTextContent("Loading the page");
  expect(screen.getByRole("status")).toHaveFocus();
  const heading = await screen.findByRole("heading", { name: "Change log", level: 1 });
  expect(heading).toHaveFocus();
  expect(screen.queryByText(loadProblem)).not.toBeInTheDocument();
  expect(download.attempts).toBe(3);
});

it("says something went wrong, without blaming the connection, when a page fails while it renders", async () => {
  const logged = vi.spyOn(console, "error").mockImplementation(() => {});
  crash.on = true;
  const menu = signIn();

  fireEvent.click(await menu.findByRole("button", { name: "PSV companies" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on this page.");
  expect(screen.queryByText(loadProblem)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reload the app" })).toBeInTheDocument();
  expect(logged.mock.calls.some((call) => call.includes(crash.error))).toBe(true);

  // Still broken: the problem shows again, with focus kept on Try again.
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on this page.");
  expect(screen.getByRole("button", { name: "Try again" })).toHaveFocus();

  crash.on = false;
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("heading", { name: "PSV companies", level: 1 })).toHaveFocus();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
