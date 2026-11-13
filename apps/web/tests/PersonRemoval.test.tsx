import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { PeopleAccessView } from "../components/PeopleAccessView";
import { fakeApi } from "./fakeApi";
import {
  catalogFixture,
  peoplePage,
  personFixture,
  problem,
  rolesFixture,
  scopeOptionsFixture,
} from "./fixtures";
import { renderInApp } from "./renderInApp";

const PEOPLE = "setup/people?page=1&pageSize=25";
const MANAGER = [
  "people.view",
  "people.add",
  "people.edit",
  "people.block",
  "people.sign_in",
  "revenue.view",
  "revenue.capture",
];
const DELETER = MANAGER;
const IN_USE = "This record is in use, so it cannot be deleted.";

const grace = (over: object = {}) =>
  personFixture({ status: "active", modules: [], everything: false, ...over });

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on(PEOPLE, [200, peoplePage([grace()])]);
  fake.on("setup/access/catalog", [200, catalogFixture]);
  fake.on("setup/access/roles", [200, rolesFixture]);
  fake.on("setup/access/scope-options", [200, scopeOptionsFixture]);
  fake.on("setup/access/me", [
    200,
    { allCompanies: true, companies: [], vehicles: [], canChange: "Any date" },
  ]);
  fake.on("setup/people/*", [200, grace()]);
  fake.on("POST setup/people", [200, { id: "person-1" }]);
});

const open = (session: object = {}) =>
  renderInApp(
    <PeopleAccessView />,
    { role: "Office admin", permissions: MANAGER, ...session },
    { businessDate: "2026-10-12" },
  );

async function openEditor(name = "Grace Achieng") {
  fireEvent.click(await screen.findByRole("button", { name: `Edit ${name}` }));
  return screen.findByRole("dialog", { name });
}

async function openRemovePane(session: object = { permissions: DELETER }) {
  open(session);
  const editor = await openEditor();
  fireEvent.click(
    within(editor).getByRole("button", { name: /^Block or delete/ }),
  );
  return editor;
}

const peopleLoads = () =>
  fake.calls.filter((call) => call.path === PEOPLE).length;

it("puts Block, Erase and Delete in the person pop up, each with what it does", async () => {
  const editor = await openRemovePane();
  expect(within(editor).getByText(/can unblock them later/)).toBeVisible();
  expect(
    within(editor).getByText(/Money records stay, shown as Former member/),
  ).toBeVisible();
  expect(
    within(editor).getByText(/removes them from this organization/),
  ).toBeVisible();
  expect(
    within(editor).getByRole("button", { name: "Erase Grace" }),
  ).toBeDisabled();
  expect(within(editor).getByText(/Block Grace first/)).toBeVisible();
  fireEvent.click(within(editor).getByRole("button", { name: "Block Grace" }));
  expect(
    await screen.findByRole("dialog", { name: "Block person" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("dialog", { name: "Grace Achieng" }),
  ).not.toBeInTheDocument();
});

it("offers Erase from the pop up once the person is blocked", async () => {
  fake.on(PEOPLE, [
    200,
    peoplePage([grace({ status: "blocked", active: false })]),
  ]);
  const editor = await openRemovePane();
  fireEvent.click(within(editor).getByRole("button", { name: "Erase Grace" }));
  expect(
    await screen.findByRole("dialog", { name: "Erase person" }),
  ).toBeInTheDocument();
});

it("deletes a person only after the consequence is shown, then reloads the list", async () => {
  fake.on("DELETE setup/people/person-2", [200, { id: "person-2" }]);
  const editor = await openRemovePane();
  fireEvent.click(within(editor).getByRole("button", { name: "Delete Grace" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete person" });
  expect(within(dialog).getByText(/cannot be undone/)).toBeInTheDocument();
  expect(
    within(dialog).getByText(/removed from this organization/),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText(/only while they have no records/),
  ).toBeInTheDocument();
  expect(fake.calls.some((call) => call.method === "DELETE")).toBe(false);
  const loads = peopleLoads();
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Delete permanently" }),
  );
  expect(await screen.findByText("Grace Achieng deleted")).toBeInTheDocument();
  expect(
    fake.calls
      .filter((call) => call.method === "DELETE")
      .map((call) => call.path),
  ).toEqual(["setup/people/person-2"]);
  await waitFor(() => expect(peopleLoads()).toBe(loads + 1));
});

it("shows the server's answer for someone with records, and offers Block instead", async () => {
  fake.on(
    "DELETE setup/people/person-2",
    problem(409, IN_USE, "Grace Achieng has records: block them instead."),
  );
  const editor = await openRemovePane();
  fireEvent.click(within(editor).getByRole("button", { name: "Delete Grace" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete person" });
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Delete permanently" }),
  );
  expect(
    await within(dialog).findByText(
      "Grace Achieng has records: block them instead.",
    ),
  ).toBeInTheDocument();
  expect(
    within(dialog).queryByRole("button", { name: "Delete permanently" }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Block instead" }),
  );
  const block = await screen.findByRole("dialog", { name: "Block person" });
  expect(within(block).getByText("Grace Achieng")).toBeInTheDocument();
  expect(
    screen.queryByRole("dialog", { name: "Delete person" }),
  ).not.toBeInTheDocument();
});

it("offers Erase instead for a blocked person with records", async () => {
  fake.on(PEOPLE, [
    200,
    peoplePage([grace({ status: "blocked", active: false })]),
  ]);
  fake.on(
    "DELETE setup/people/person-2",
    problem(409, IN_USE, "Grace Achieng has records: block them instead."),
  );
  const editor = await openRemovePane();
  fireEvent.click(within(editor).getByRole("button", { name: "Delete Grace" }));
  const dialog = await screen.findByRole("dialog", { name: "Delete person" });
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Delete permanently" }),
  );
  fireEvent.click(
    await within(dialog).findByRole("button", { name: "Erase instead" }),
  );
  expect(
    await screen.findByRole("dialog", { name: "Erase person" }),
  ).toBeInTheDocument();
});

it("hides Block or delete for yourself, and for the Owner unless you are the Owner", async () => {
  fake.on(PEOPLE, [
    200,
    peoplePage([
      grace({ id: "me", firstName: "Test", lastName: "User" }),
      grace({
        id: "person-3",
        firstName: "Olive",
        lastName: "Owner",
        role: "Owner",
      }),
    ]),
  ]);
  const view = open({ permissions: DELETER });
  let editor = await openEditor("Test User");
  expect(
    within(editor).queryByRole("button", { name: /^Block or delete/ }),
  ).not.toBeInTheDocument();
  fireEvent.click(
    within(editor).getAllByRole("button", { name: "Close" }).at(-1)!,
  );
  editor = await openEditor("Olive Owner");
  expect(
    within(editor).queryByRole("button", { name: /^Block or delete/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Block Olive Owner" }),
  ).not.toBeInTheDocument();
  view.unmount();

  open({ role: "Owner", permissions: DELETER });
  editor = await openEditor("Olive Owner");
  fireEvent.click(
    within(editor).getByRole("button", { name: /^Block or delete/ }),
  );
  expect(
    within(editor).getByRole("button", { name: "Delete Olive" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Block Olive Owner" }),
  ).toBeInTheDocument();
});

it("offers Delete with people.block alongside Block", async () => {
  const editor = await openRemovePane({ permissions: MANAGER });
  expect(
    within(editor).getByRole("button", { name: "Block Grace" }),
  ).toBeVisible();
  expect(
    within(editor).getByRole("button", { name: "Delete Grace" }),
  ).toBeVisible();
});

it.each(["people.add", "people.sign_in"])(
  "hides Block or delete when %s grants people.manage without people.block",
  async (right) => {
    open({
      permissions: ["people.view", "people.edit", right, "people.manage"],
    });
    const editor = await openEditor();
    await within(editor).findByRole("button", { name: /^Access/ });
    expect(
      within(editor).queryByRole("button", { name: /^Block or delete/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete Grace" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Block Grace Achieng" }),
    ).not.toBeInTheDocument();
  },
);

it("hides Block or delete without people.block", async () => {
  open({ permissions: ["people.view", "people.edit"] });
  const editor = await openEditor();
  await within(editor).findByRole("button", { name: /^Access/ });
  expect(
    within(editor).queryByRole("button", { name: /^Block or delete/ }),
  ).not.toBeInTheDocument();
});

it("lists the organization's own roles in the job picker and fills their defaults", async () => {
  fake.on("setup/access/roles", [
    200,
    [
      ...rolesFixture.map((role) => ({ ...role, builtIn: true })),
      {
        id: "role-9",
        name: "Night shift",
        permissions: ["revenue.view"],
        builtIn: false,
        version: 1,
      },
    ],
  ]);
  open({ role: "Owner" });
  fireEvent.click(await screen.findByRole("button", { name: "New person" }));
  const editor = await screen.findByRole("dialog", { name: "New person" });
  const job = (await within(editor).findByLabelText(
    "Job",
  )) as HTMLSelectElement;
  const own = within(job).getByRole("group", { name: "Your roles" });
  expect(
    within(own)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["Night shift"]);
  fireEvent.change(job, { target: { value: "Night shift" } });
  fireEvent.click(within(editor).getByRole("button", { name: /^Access/ }));
  expect(
    within(editor).getByRole("checkbox", { name: "View revenue records" }),
  ).toBeChecked();
  expect(
    within(editor).getByRole("checkbox", { name: "Capture revenue" }),
  ).not.toBeChecked();
  fireEvent.change(job, { target: { value: "Revenue clerk" } });
  expect(
    within(editor).getByRole("checkbox", { name: "Capture revenue" }),
  ).toBeChecked();
});
