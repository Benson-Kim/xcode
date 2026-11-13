import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { RolesPage } from "../components/people/RolesPage";
import { fakeApi } from "./fakeApi";
import { catalogFixture, problem } from "./fixtures";
import { renderInApp } from "./renderInApp";

const ROLES = "setup/access/roles";
const MANAGER = [
  "people.view",
  "access.manage",
  "revenue.view",
  "revenue.capture",
  "reports.view",
];

const nightShift = (over: object = {}) => ({
  id: "role-9",
  name: "Night shift",
  permissions: ["revenue.view"],
  builtIn: false,
  version: 4,
  ...over,
});
const roles = [
  {
    id: "role-1",
    name: "Revenue clerk",
    permissions: ["revenue.view", "revenue.capture"],
  },
  nightShift(),
  {
    id: "role-2",
    name: "Accountant",
    permissions: ["reports.view"],
    builtIn: true,
  },
];

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on(ROLES, [200, roles]);
  fake.on("setup/access/catalog", [200, catalogFixture]);
  fake.on(`POST ${ROLES}`, [
    200,
    nightShift({ id: "role-10", name: "Day shift" }),
  ]);
  fake.on(`PUT ${ROLES}/*`, [200, nightShift({ version: 5 })]);
});

const open = (permissions = MANAGER) =>
  renderInApp(<RolesPage />, { role: "Office admin", permissions });

const roleLoads = () =>
  fake.calls.filter((call) => call.method === "GET" && call.path === ROLES)
    .length;

const ticked = (dialog: HTMLElement, label: string) =>
  (within(dialog).getByRole("checkbox", { name: label }) as HTMLInputElement)
    .checked;

it("lists the built-in roles first, marked Built in and read only, then the organization's own", async () => {
  open();
  await screen.findByRole("button", { name: "Edit Night shift" });
  const rows = screen.getAllByRole("row").slice(1);
  expect(rows.map((row) => row.textContent)).toEqual([
    expect.stringMatching(/^Accountant Built in1 of 3/),
    expect.stringMatching(/^Revenue clerk Built in2 of 3/),
    expect.stringMatching(/^Night shift 1 of 3/),
  ]);
  expect(
    screen.getByRole("button", { name: "View Revenue clerk" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Edit Revenue clerk" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Delete Accountant" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Delete Night shift" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add role" })).toBeInTheDocument();
});

it("offers no Add, Edit or Delete without access.manage", async () => {
  open(["people.view"]);
  fireEvent.click(
    await screen.findByRole("button", { name: "View Night shift" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Night shift" });
  expect(
    within(dialog).queryByRole("button", { name: "Save" }),
  ).not.toBeInTheDocument();
  expect(
    within(dialog).getByRole("checkbox", { name: "View revenue records" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Add role" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /^(Edit|Delete) / }),
  ).not.toBeInTheDocument();
});

it("only shows a role holding a permission the manager lacks, with why", async () => {
  open(["people.view", "access.manage"]);
  fireEvent.click(
    await screen.findByRole("button", { name: "View Night shift" }),
  );
  expect(
    screen.queryByRole("button", { name: "Delete Night shift" }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add role" })).toBeInTheDocument();
  const dialog = await screen.findByRole("dialog", { name: "Night shift" });
  expect(
    within(dialog).getByText(/only when you hold all of its permissions/),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByRole("checkbox", { name: "View revenue records" }),
  ).toBeDisabled();
  expect(
    within(dialog).queryByRole("button", { name: "Save" }),
  ).not.toBeInTheDocument();
});

it("shows a built-in role read only, with why", async () => {
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "View Revenue clerk" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Revenue clerk" });
  expect(within(dialog).getByText(/cannot be changed/)).toBeInTheDocument();
  expect(ticked(dialog, "Capture revenue")).toBe(true);
  expect(
    within(dialog).getByRole("checkbox", { name: "Capture revenue" }),
  ).toBeDisabled();
  expect(
    within(dialog).queryByRole("button", { name: "Save" }),
  ).not.toBeInTheDocument();
});

it("adds a role: a unique name, at least one permission, and what each right needs", async () => {
  open();
  fireEvent.click(await screen.findByRole("button", { name: "Add role" }));
  const dialog = await screen.findByRole("dialog", { name: "Add role" });
  await within(dialog).findByRole("checkbox", { name: "Capture revenue" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(
    await within(dialog).findByText("Enter the role's name."),
  ).toBeInTheDocument();
  expect(within(dialog).getByText("Tick at least one.")).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Name"), {
    target: { value: "  night SHIFT " },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(
    await within(dialog).findByText("Another role already has this name."),
  ).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Name"), {
    target: { value: " Day shift " },
  });
  fireEvent.click(
    within(dialog).getByRole("checkbox", { name: "Capture revenue" }),
  );
  expect(ticked(dialog, "View revenue records")).toBe(true);
  expect(fake.sent(`POST ${ROLES}`)).toHaveLength(0);
  const loads = roleLoads();
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(fake.sent(`POST ${ROLES}`)).toHaveLength(1));
  const [body] = fake.sent(`POST ${ROLES}`);
  expect(body.name).toBe("Day shift");
  expect([...(body.permissions as string[])].sort()).toEqual([
    "revenue.capture",
    "revenue.view",
  ]);
  expect(await screen.findByText("Day shift added.")).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: "Add role" }),
    ).not.toBeInTheDocument(),
  );
  await waitFor(() => expect(roleLoads()).toBe(loads + 1));
});

it("edits a role with the version it was based on, and unticking a right unticks what needs it", async () => {
  fake.on(ROLES, [
    200,
    [nightShift({ permissions: ["revenue.view", "revenue.capture"] })],
  ]);
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Night shift" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Edit role" });
  expect(within(dialog).getByLabelText("Name")).toHaveValue("Night shift");
  fireEvent.click(
    within(dialog).getByRole("checkbox", { name: "View revenue records" }),
  );
  expect(ticked(dialog, "Capture revenue")).toBe(false);
  fireEvent.click(
    within(dialog).getByRole("checkbox", { name: "View reports" }),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(fake.sent(`PUT ${ROLES}/role-9`)).toEqual([
      { name: "Night shift", permissions: ["reports.view"], version: 4 },
    ]),
  );
  expect(await screen.findByText("Night shift saved.")).toBeInTheDocument();
});

it("reloads a role someone else changed first, and says so", async () => {
  fake.on(
    `PUT ${ROLES}/role-9`,
    problem(409, "Settings changed. Reload before saving."),
  );
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Night shift" }),
  );
  let dialog = await screen.findByRole("dialog", { name: "Edit role" });
  fireEvent.click(
    within(dialog).getByRole("checkbox", { name: "View reports" }),
  );
  fake.on(ROLES, [
    200,
    [
      nightShift({
        permissions: ["revenue.view", "revenue.capture"],
        version: 5,
      }),
    ],
  ]);
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() => {
    dialog = screen.getByRole("dialog", { name: "Edit role" });
    expect(
      within(dialog).getByText(/Someone else changed this role/),
    ).toBeInTheDocument();
    expect(ticked(dialog, "Capture revenue")).toBe(true);
  });
  expect(ticked(dialog, "View reports")).toBe(false);
  fireEvent.click(
    within(dialog).getByRole("checkbox", { name: "View reports" }),
  );
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(fake.sent(`PUT ${ROLES}/role-9`).at(-1)).toMatchObject({
      version: 5,
    }),
  );
});

it("shows a name clash the server found as it says it, without reloading", async () => {
  fake.on(
    `PUT ${ROLES}/role-9`,
    problem(400, "Invalid setup change", "Another role already has this name."),
  );
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Night shift" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Edit role" });
  const loads = roleLoads();
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  expect(
    await within(dialog).findByText("Another role already has this name."),
  ).toBeInTheDocument();
  expect(
    within(dialog).queryByText(/Someone else changed this role/),
  ).not.toBeInTheDocument();
  expect(roleLoads()).toBe(loads);
});

it("deletes a role only after confirming, and shows the server's answer while people hold it", async () => {
  fake.once(
    `DELETE ${ROLES}/role-9`,
    problem(
      409,
      "This record is in use, so it cannot be deleted.",
      "Night shift is held by 2 people: give them another role first.",
    ),
  );
  fake.on(`DELETE ${ROLES}/role-9`, [200, { id: "role-9" }]);
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "Delete Night shift" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Delete role" });
  expect(
    within(dialog).getByText(/only while nobody holds it/),
  ).toBeInTheDocument();
  expect(fake.calls.some((call) => call.method === "DELETE")).toBe(false);
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(
    await within(dialog).findByText(
      "Night shift is held by 2 people: give them another role first.",
    ),
  ).toBeInTheDocument();
  const loads = roleLoads();
  fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("Night shift deleted.")).toBeInTheDocument();
  await waitFor(() => expect(roleLoads()).toBe(loads + 1));
});
