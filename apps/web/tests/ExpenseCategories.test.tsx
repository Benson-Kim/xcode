import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ExpenseCategoriesPage } from "../components/setup";
import type { ExpenseCategory } from "../lib/types";
import { renderInApp } from "./renderInApp";

const catalog: ExpenseCategory[] = [
  {
    id: "loans",
    name: "Loans",
    bucket: 3,
    active: true,
    stoppedOn: null,
    items: [
      {
        id: "loan",
        categoryId: "loans",
        name: "Loan repayment",
        active: true,
        stoppedOn: null,
      },
    ],
  },
  {
    id: "garage",
    name: "Garage and repairs",
    bucket: 1,
    active: true,
    stoppedOn: null,
    items: [
      {
        id: "tyres",
        categoryId: "garage",
        name: "Tyres",
        active: true,
        stoppedOn: null,
      },
      {
        id: "spares",
        categoryId: "garage",
        name: "Spares",
        active: false,
        stoppedOn: "2026-09-10",
      },
    ],
  },
  {
    id: "old",
    name: "Old charges",
    bucket: 2,
    active: false,
    stoppedOn: "2026-09-01",
    items: [],
  },
];

function serve() {
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) =>
    init?.method
      ? new Response(JSON.stringify({ id: "new-id" }), { status: 200 })
      : new Response(
          JSON.stringify({
            items: catalog,
            pageNumber: 1,
            pageSize: 100,
            total: catalog.length,
          }),
          { status: 200 },
        ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const writes = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls
    .filter(([, init]) => init?.method)
    .map(([url, init]) => [url, init!.method, JSON.parse(String(init!.body))]);

const panelRows = () =>
  screen.getByRole("tabpanel").querySelectorAll("tbody > tr").length;

it("lists items with their category, and categories grouped by bucket, read-only without expenses.setup", async () => {
  const fetchMock = serve();
  renderInApp(<ExpenseCategoriesPage canManage={false} />, {
    permissions: ["commitments.view"],
  });

  expect(await screen.findByText("Tyres")).toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    "/api/setup/expense-categories?page=1&pageSize=100",
  ]);
  const tyres = screen.getByRole("row", { name: /Tyres/ });
  expect(within(tyres).getByText("Garage and repairs")).toBeInTheDocument();
  expect(
    within(tyres).getByTitle("Counts as Repairs and maintenance"),
  ).toHaveTextContent("Garage and repairs");
  expect(within(tyres).getByText("In use")).toBeInTheDocument();
  expect(
    within(screen.getByRole("row", { name: /Spares/ })).getByText("Turned off"),
  ).toBeInTheDocument();
  expect(screen.getByText("3 items")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /New|Add|Edit|Turn/ }),
  ).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Show"), { target: { value: "on" } });
  expect(screen.queryByText("Spares")).not.toBeInTheDocument();
  expect(screen.getByText("2 items")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: /^Categories/ }));
  expect(screen.getByRole("tab", { name: /^Categories/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  fireEvent.change(screen.getByLabelText("Show"), { target: { value: "all" } });
  const names = [
    ...screen
      .getByRole("tabpanel")
      .querySelectorAll("tbody > tr > td:first-child"),
  ].map((cell) => cell.textContent);
  expect(names).toEqual(["Garage and repairs", "Old charges", "Loans"]);
  expect(
    within(screen.getByRole("row", { name: /Loans/ })).getByText(
      "Loan repayments",
    ),
  ).toBeInTheDocument();
  expect(panelRows()).toBe(3);
});

it("moves between the tabs with the arrow keys", async () => {
  serve();
  renderInApp(<ExpenseCategoriesPage canManage={false} />);
  await screen.findByText("Tyres");

  const items = screen.getByRole("tab", { name: /^Items/ });
  items.focus();
  fireEvent.keyDown(items, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: /^Categories/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.getByRole("tab", { name: /^Categories/ })).toHaveFocus();
  expect(screen.getByRole("tabpanel")).toHaveAttribute(
    "aria-labelledby",
    "expenses-tab-categories",
  );
});

it("adds a category and an item, refusing names already taken", async () => {
  const fetchMock = serve();
  renderInApp(<ExpenseCategoriesPage canManage />, {
    permissions: ["expenses.setup"],
  });
  await screen.findByText("Tyres");

  fireEvent.click(screen.getByRole("tab", { name: /^Categories/ }));
  fireEvent.click(screen.getByRole("button", { name: "New category" }));
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "loans" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "That category already exists.",
  );
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Fuel and road" },
  });
  fireEvent.change(screen.getByLabelText("Counts as"), {
    target: { value: "2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(writes(fetchMock)).toEqual([
      [
        "/api/setup/expense-categories",
        "POST",
        { name: "Fuel and road", bucket: 2 },
      ],
    ]),
  );
  expect(await screen.findByText("Fuel and road added.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: /^Items/ }));
  fireEvent.click(screen.getByRole("button", { name: "New item" }));
  const dialog = within(screen.getByRole("dialog", { name: "New item" }));
  fireEvent.change(dialog.getByLabelText("Category"), {
    target: { value: "garage" },
  });
  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "TYRES" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "That item already exists in this category.",
  );
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Towing" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(fetchMock)).toHaveLength(2));
  expect(writes(fetchMock)[1]).toEqual([
    "/api/setup/expense-categories/garage/items",
    "POST",
    { name: "Towing" },
  ]);
});

it("renames, changes the bucket, turns off and turns on", async () => {
  const fetchMock = serve();
  renderInApp(<ExpenseCategoriesPage canManage />, {
    permissions: ["expenses.setup"],
  });
  await screen.findByText("Tyres");

  fireEvent.click(screen.getByRole("button", { name: "Edit Tyres" }));
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Tyres and tubes" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(writes(fetchMock)).toEqual([
      ["/api/setup/expense-items/tyres", "PUT", { name: "Tyres and tubes" }],
    ]),
  );

  fireEvent.click(screen.getByRole("button", { name: "Turn on Spares" }));
  await waitFor(() =>
    expect(writes(fetchMock)[1]).toEqual([
      "/api/setup/expense-items/spares/restore",
      "POST",
      {},
    ]),
  );
  expect(await screen.findByText("Spares turned on.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: /^Categories/ }));
  fireEvent.click(screen.getByRole("button", { name: "Edit Loans" }));
  fireEvent.change(screen.getByLabelText("Counts as"), {
    target: { value: "2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(writes(fetchMock)[2]).toEqual([
      "/api/setup/expense-categories/loans",
      "PUT",
      { name: "Loans", bucket: 2 },
    ]),
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Turn off Garage and repairs" }),
  );
  await waitFor(() =>
    expect(writes(fetchMock)[3]).toEqual([
      "/api/setup/expense-categories/garage/stop",
      "POST",
      {},
    ]),
  );
});

it("says why when the server refuses a change", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_input: string, init?: RequestInit) =>
      init?.method
        ? new Response(
            JSON.stringify({
              title: "Not permitted in this organization or data scope.",
              detail: "Only people who set up expenses can change categories.",
            }),
            { status: 403 },
          )
        : new Response(
            JSON.stringify({
              items: catalog,
              pageNumber: 1,
              pageSize: 100,
              total: catalog.length,
            }),
            { status: 200 },
          ),
    ),
  );
  renderInApp(<ExpenseCategoriesPage canManage />, {
    permissions: ["expenses.setup"],
  });

  fireEvent.click(
    await screen.findByRole("button", { name: "Turn off Tyres" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Only people who set up expenses can change categories.",
  );
});

it("cancels a stop dated ahead of the business date with Turn on instead of stopping again", async () => {
  const scheduled: ExpenseCategory[] = [
    {
      id: "soon",
      name: "Soon off",
      bucket: 2,
      active: true,
      stoppedOn: "2026-09-25",
      items: [
        {
          id: "later",
          categoryId: "soon",
          name: "Later item",
          active: true,
          stoppedOn: "2026-09-26",
        },
      ],
    },
  ];
  const fetchMock = vi.fn(async (_input: string, init?: RequestInit) =>
    init?.method
      ? new Response(JSON.stringify({ id: "x" }), { status: 200 })
      : new Response(
          JSON.stringify({
            items: scheduled,
            pageNumber: 1,
            pageSize: 100,
            total: 1,
          }),
          { status: 200 },
        ),
  );
  vi.stubGlobal("fetch", fetchMock);
  renderInApp(<ExpenseCategoriesPage canManage />, {
    permissions: ["expenses.setup"],
  });

  expect(await screen.findByText(/Turns off on/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Turn on Later item" }));
  await waitFor(() =>
    expect(writes(fetchMock as ReturnType<typeof serve>)).toEqual([
      ["/api/setup/expense-items/later/restore", "POST", {}],
    ]),
  );
  fireEvent.click(screen.getByRole("tab", { name: /^Categories/ }));
  fireEvent.click(screen.getByRole("button", { name: "Turn on Soon off" }));
  await waitFor(() =>
    expect(writes(fetchMock as ReturnType<typeof serve>)[1]).toEqual([
      "/api/setup/expense-categories/soon/restore",
      "POST",
      {},
    ]),
  );
});
