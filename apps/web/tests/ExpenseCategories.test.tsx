import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { ExpenseCategoriesPage } from "../components/setup";
import type { ExpenseCategory, ExpenseMainCategory } from "../lib/types";
import { fakeApi } from "./fakeApi";
import { renderInApp } from "./renderInApp";

const mains: ExpenseMainCategory[] = [
  { id: "m-run", name: "Running costs", categoryCount: 1, itemCount: 2 },
  { id: "m-fin", name: "Finance", categoryCount: 1, itemCount: 1 },
];

const catalog: ExpenseCategory[] = [
  {
    id: "loans",
    name: "Loans",
    bucket: null,
    active: true,
    stoppedOn: null,
    mainCategoryId: "m-fin",
    mainCategoryName: "Finance",
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
    bucket: null,
    active: true,
    stoppedOn: null,
    mainCategoryId: "m-run",
    mainCategoryName: "Running costs",
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
    bucket: null,
    active: true,
    stoppedOn: null,
    mainCategoryId: null,
    mainCategoryName: null,
    items: [],
  },
];

const page = <T,>(items: T[]) =>
  [200, { items, pageNumber: 1, pageSize: 100, total: items.length }] as const;

function serve(
  data: { categories?: ExpenseCategory[]; mains?: ExpenseMainCategory[] } = {},
) {
  const api = fakeApi();
  api.on("GET setup/expense-categories*", page(data.categories ?? catalog));
  api.on("GET setup/expense-main-categories*", page(data.mains ?? mains));
  for (const key of [
    "POST setup/expense-main-categories",
    "PUT setup/expense-main-categories/*",
    "POST setup/expense-categories",
    "PUT setup/expense-categories/*",
    "POST setup/expense-categories/*",
    "PUT setup/expense-items/*",
    "POST setup/expense-items/*",
  ])
    api.on(key, [200, { id: "new-id" }]);
  return api;
}

const writes = (api: ReturnType<typeof serve>) =>
  api.calls
    .filter((call) => call.method !== "GET")
    .map((call) => [call.method, call.path, call.body]);

const reads = (api: ReturnType<typeof serve>, path: string) =>
  api.calls.filter(
    (call) => call.method === "GET" && call.path.startsWith(path),
  ).length;

const tab = (name: RegExp) => screen.getByRole("tab", { name });

it("lists the three tabs with their counts and tables, read-only with only catalog.view", async () => {
  const api = serve();
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.view"] });

  expect(await screen.findByText("Tyres")).toBeInTheDocument();
  expect(api.calls.map((call) => call.path).sort()).toEqual([
    "setup/expense-categories?page=1&pageSize=100",
    "setup/expense-main-categories?page=1&pageSize=100",
  ]);
  expect(screen.getByRole("heading", { name: "Expense items" })).toBeVisible();
  expect(screen.getByRole("tablist")).toHaveClass("tabs", "three");
  expect(tab(/^Main categories/)).toHaveTextContent("Main categories2");
  expect(tab(/^Categories/)).toHaveTextContent(
    "Categories3, 1 with no main category",
  );
  expect(tab(/^Items/)).toHaveTextContent("Items2 in use");
  expect(tab(/^Items/)).toHaveAttribute("aria-selected", "true");

  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Item", "Category", "Main category", "Status"]);
  const tyres = screen.getByRole("row", { name: /Tyres/ });
  expect(within(tyres).getByText("Garage and repairs")).toBeInTheDocument();
  expect(within(tyres).getByText("Running costs")).toBeInTheDocument();
  expect(within(tyres).getByText("In use")).toHaveClass("chip", "ok");
  expect(
    within(screen.getByRole("row", { name: /Spares/ })).getByText("Stopped"),
  ).toHaveClass("chip", "wait");
  expect(
    screen.queryByRole("button", { name: /New|Edit|Stop|Resume/ }),
  ).not.toBeInTheDocument();

  fireEvent.click(tab(/^Categories/));
  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Category", "Main category", "Items"]);
  const old = screen.getByRole("row", { name: /Old charges/ });
  expect(within(old).getByText("Not set")).toHaveClass("chip", "mute");
  const garage = screen.getByRole("row", { name: /Garage and repairs/ });
  expect(garage.querySelectorAll("td")[2]).toHaveTextContent("2");

  fireEvent.click(tab(/^Main categories/));
  expect(
    screen.getAllByRole("columnheader").map((header) => header.textContent),
  ).toEqual(["Main category", "Categories", "Items"]);
  const running = screen.getByRole("row", { name: /Running costs/ });
  expect(
    [...running.querySelectorAll("td")].map((cell) => cell.textContent),
  ).toEqual(["Running costs", "1", "2"]);
});

it("says so when there are no main categories or categories yet", async () => {
  serve({ categories: [], mains: [] });
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.view"] });

  fireEvent.click(await screen.findByRole("tab", { name: /^Categories/ }));
  expect(await screen.findByText("No categories yet.")).toBeInTheDocument();
  fireEvent.click(tab(/^Main categories/));
  expect(screen.getByText("No main categories yet.")).toBeInTheDocument();
});

it("moves between the tabs with the arrow keys", async () => {
  serve();
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.view"] });
  await screen.findByText("Tyres");

  const items = tab(/^Items/);
  items.focus();
  fireEvent.keyDown(items, { key: "ArrowLeft" });
  expect(tab(/^Categories/)).toHaveAttribute("aria-selected", "true");
  expect(tab(/^Categories/)).toHaveFocus();
  expect(screen.getByRole("tabpanel")).toHaveAttribute(
    "aria-labelledby",
    "expenses-tab-cats",
  );
});

it("offers the new button of the tab shown, only with catalog.add", async () => {
  serve();
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.add"] });
  await screen.findByText("Tyres");

  expect(screen.getByRole("button", { name: "New item" })).toBeInTheDocument();
  fireEvent.click(tab(/^Categories/));
  expect(
    screen.getByRole("button", { name: "New category" }),
  ).toBeInTheDocument();
  fireEvent.click(tab(/^Main categories/));
  expect(
    screen.getByRole("button", { name: "New main category" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /^Edit/ }),
  ).not.toBeInTheDocument();
});

it("adds a main category, refusing an empty name and one already here", async () => {
  const api = serve();
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.add"] });
  await screen.findByText("Tyres");

  fireEvent.click(tab(/^Main categories/));
  fireEvent.click(screen.getByRole("button", { name: "New main category" }));
  const dialog = within(
    screen.getByRole("dialog", { name: "New main category" }),
  );
  expect(dialog.queryByLabelText("Main category")).not.toBeInTheDocument();
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the main category name.",
  );
  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "finance" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "finance is already here.",
  );
  expect(writes(api)).toEqual([]);

  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "Fuel and road" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(writes(api)).toEqual([
      ["POST", "setup/expense-main-categories", { name: "Fuel and road" }],
    ]),
  );
  expect(await screen.findByText("Main category added")).toBeInTheDocument();
  await waitFor(() =>
    expect(reads(api, "setup/expense-main-categories")).toBe(2),
  );
  expect(reads(api, "setup/expense-categories")).toBe(2);
});

it("renames a main category with PUT, and shows the server's refusal", async () => {
  const api = serve();
  api.on("PUT setup/expense-main-categories/m-fin", [
    409,
    { title: "Conflict", detail: "Finance was changed by someone else." },
  ]);
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.edit"] });
  await screen.findByText("Tyres");

  fireEvent.click(tab(/^Main categories/));
  fireEvent.click(screen.getByRole("button", { name: "Edit Finance" }));
  const dialog = within(
    screen.getByRole("dialog", { name: "Edit main category" }),
  );
  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "Money" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(await dialog.findByRole("alert")).toHaveTextContent(
    "Finance was changed by someone else.",
  );
  expect(writes(api)).toEqual([
    ["PUT", "setup/expense-main-categories/m-fin", { name: "Money" }],
  ]);
});

it("adds a category under a main category, or under none, with no Counts as control", async () => {
  const api = serve();
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.add"] });
  await screen.findByText("Tyres");

  fireEvent.click(tab(/^Categories/));
  fireEvent.click(screen.getByRole("button", { name: "New category" }));
  const dialog = within(screen.getByRole("dialog", { name: "New category" }));
  expect(dialog.queryByLabelText("Counts as")).not.toBeInTheDocument();
  const select = dialog.getByLabelText("Main category");
  expect(
    within(select)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["No main category", "Running costs", "Finance"]);
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent(
    "Enter the category name.",
  );
  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "LOANS" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent("LOANS is already here.");

  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "Insurance" },
  });
  fireEvent.change(select, { target: { value: "m-fin" } });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/expense-categories",
    { name: "Insurance", mainCategoryId: "m-fin" },
  ]);
  expect(await screen.findByText("Category added")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "New category" }));
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Parking" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(2));
  expect(writes(api)[1]).toEqual([
    "POST",
    "setup/expense-categories",
    { name: "Parking", mainCategoryId: null },
  ]);
});

it("moves a category to another main category, or to none", async () => {
  const api = serve();
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.edit"] });
  await screen.findByText("Tyres");

  fireEvent.click(tab(/^Categories/));
  fireEvent.click(screen.getByRole("button", { name: "Edit Loans" }));
  expect(screen.getByLabelText("Main category")).toHaveValue("m-fin");
  fireEvent.change(screen.getByLabelText("Main category"), {
    target: { value: "" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "PUT",
    "setup/expense-categories/loans",
    { name: "Loans", mainCategoryId: null },
  ]);

  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Old charges" }),
  );
  fireEvent.change(screen.getByLabelText("Main category"), {
    target: { value: "m-run" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(2));
  expect(writes(api)[1]).toEqual([
    "PUT",
    "setup/expense-categories/old",
    { name: "Old charges", mainCategoryId: "m-run" },
  ]);
});

it("adds, renames and moves items on the item routes", async () => {
  const api = serve();
  renderInApp(<ExpenseCategoriesPage />, {
    permissions: ["catalog.add", "catalog.edit"],
  });
  await screen.findByText("Tyres");

  fireEvent.click(screen.getByRole("button", { name: "New item" }));
  const dialog = within(screen.getByRole("dialog", { name: "New item" }));
  fireEvent.change(dialog.getByLabelText("Category"), {
    target: { value: "garage" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent("Enter the item name.");
  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "TYRES" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(dialog.getByRole("alert")).toHaveTextContent("TYRES is already here.");
  fireEvent.change(dialog.getByLabelText("Name"), {
    target: { value: "Towing" },
  });
  fireEvent.click(dialog.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/expense-categories/garage/items",
    { name: "Towing" },
  ]);
  expect(await screen.findByText("Item added")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Edit Tyres" }));
  fireEvent.change(screen.getByLabelText("Name"), {
    target: { value: "Tyres and tubes" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(2));
  expect(writes(api)[1]).toEqual([
    "PUT",
    "setup/expense-items/tyres",
    { name: "Tyres and tubes" },
  ]);

  fireEvent.click(screen.getByRole("button", { name: "Edit Loan repayment" }));
  fireEvent.change(screen.getByLabelText("Category"), {
    target: { value: "garage" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(writes(api)).toHaveLength(3));
  expect(writes(api)[2]).toEqual([
    "PUT",
    "setup/expense-items/loan",
    { name: "Loan repayment", categoryId: "garage" },
  ]);
});

it("stops and resumes an item with catalog.stop, and shows why a stop is refused", async () => {
  const api = serve();
  api.on("POST setup/expense-items/loan/stop", [
    403,
    { title: "Forbidden", detail: "Loan repayment is still scheduled." },
  ]);
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.stop"] });
  await screen.findByText("Tyres");

  expect(
    screen.queryByRole("button", { name: /^Edit/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Resume Spares" }));
  await waitFor(() => expect(writes(api)).toHaveLength(1));
  expect(writes(api)[0]).toEqual([
    "POST",
    "setup/expense-items/spares/restore",
    {},
  ]);
  expect(await screen.findByText("Spares resumed.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Stop Tyres" }));
  await waitFor(() =>
    expect(writes(api)[1]).toEqual([
      "POST",
      "setup/expense-items/tyres/stop",
      {},
    ]),
  );

  fireEvent.click(screen.getByRole("button", { name: "Stop Loan repayment" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Loan repayment is still scheduled.",
  );
});

it("cancels a stop dated ahead of the business date with Resume instead of stopping again", async () => {
  const api = serve({
    categories: [
      {
        id: "soon",
        name: "Soon off",
        bucket: null,
        active: true,
        stoppedOn: null,
        mainCategoryId: null,
        mainCategoryName: null,
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
    ],
  });
  renderInApp(<ExpenseCategoriesPage />, { permissions: ["catalog.stop"] });

  expect(await screen.findByText("Stops 26 Sep 2026")).toHaveClass(
    "chip",
    "wait",
  );
  fireEvent.click(screen.getByRole("button", { name: "Resume Later item" }));
  await waitFor(() =>
    expect(writes(api)).toEqual([
      ["POST", "setup/expense-items/later/restore", {}],
    ]),
  );
});

it("treats the released expenses.setup key as every catalog right", async () => {
  serve();
  renderInApp(<ExpenseCategoriesPage canManage />, {
    permissions: ["expenses.setup"],
  });
  await screen.findByText("Tyres");

  expect(screen.getByRole("button", { name: "New item" })).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Edit Tyres" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Stop Tyres" }),
  ).toBeInTheDocument();
});
