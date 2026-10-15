import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { PeopleAccessView } from "../components/PeopleAccessView";
import { fakeApi, type Sent } from "./fakeApi";
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

// The v2.33 catalogue, in part: modules with a base right, and the petty cash sections.
const catalogue = [
  ...catalogFixture,
  {
    name: "Petty cash",
    items: [
      {
        key: "pettycash.view",
        label: "View petty cash",
        needs: [],
        section: "View",
      },
      {
        key: "pettycash.spend",
        label: "Add an expense",
        needs: ["pettycash.view"],
        section: "Expenses",
      },
      {
        key: "pettycash.approve_item",
        label: "Approve an expense",
        needs: ["pettycash.view"],
        section: "Approval",
      },
    ],
  },
];

const grace = () =>
  personFixture({
    status: "active",
    lastSignedInAt: "2026-10-09T08:40:00Z",
    backLimit: { mode: "months", count: 1, from: "2026-09-14" },
    canChange: "1 month back, not before 14 September 2026",
    modules: [
      { name: "Revenue", held: 2, total: 3 },
      { name: "Petty cash", held: 0, total: 3 },
    ],
    everything: false,
    permissions: ["revenue.view", "revenue.capture", "pettycash.spend"],
  });

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on(PEOPLE, [200, peoplePage([])]);
  fake.on("setup/access/catalog", [200, catalogue]);
  fake.on("setup/access/roles", [200, rolesFixture]);
  fake.on("setup/access/scope-options", [200, scopeOptionsFixture]);
  fake.on("setup/access/me", [
    200,
    { allCompanies: true, companies: [], vehicles: [], canChange: "Any date" },
  ]);
  fake.on("POST setup/people", [200, { id: "person-1" }]);
  fake.on("POST setup/people/*", [200, { ok: true }]);
});

function open(permissions = MANAGER) {
  renderInApp(
    <PeopleAccessView />,
    { role: "Office admin", permissions },
    {
      businessDate: "2026-10-12",
    },
  );
}

async function openNewPerson() {
  open();
  fireEvent.click(await screen.findByRole("button", { name: "New person" }));
  fireEvent.change(screen.getByLabelText("First name"), {
    target: { value: "Jane" },
  });
  fireEvent.change(screen.getByLabelText("Last name"), {
    target: { value: "Njeri" },
  });
  fireEvent.change(screen.getByLabelText("Email for codes"), {
    target: { value: "jane@example.com" },
  });
  fireEvent.change(screen.getByLabelText("Mobile number"), {
    target: { value: "0711000001" },
  });
}

const pane = (name: string) =>
  fireEvent.click(
    within(screen.getByRole("navigation", { name: "Sections" })).getByRole(
      "button",
      { name: new RegExp(`^${name}`) },
    ),
  );

const lastPost = (prefix: string): Sent =>
  fake.calls.filter(
    (call) => call.method === "POST" && call.path.startsWith(prefix),
  )[
    fake.calls.filter(
      (call) => call.method === "POST" && call.path.startsWith(prefix),
    ).length - 1
  ];

it("lists each person with their modules, vehicles, how far back they may change records and their status", async () => {
  fake.on(PEOPLE, [200, peoplePage([grace()])]);
  open();
  const row = await screen.findByRole("row", { name: /Grace Achieng/ });
  expect(within(row).getByText("Float")).toHaveClass("chip");
  expect(
    within(row).getByText(/Revenue clerk · 0711 222 333/),
  ).toBeInTheDocument();
  const revenue = within(row).getByText("Revenue");
  expect(revenue).toHaveClass("mchip", "part");
  expect(revenue).toHaveTextContent("2 of 3");
  expect(within(row).queryByText("Petty cash")).not.toBeInTheDocument();
  expect(
    within(row).getByText("1 month back, not before 14 September 2026"),
  ).toBeInTheDocument();
  expect(within(row).getByText("Active")).toHaveClass("chip", "ok");
  expect(within(row).getByText(/9 Oct 2026/)).toBeInTheDocument();
  expect(
    within(row).getByRole("button", { name: "Edit Grace Achieng" }),
  ).toBeInTheDocument();
  expect(
    within(row).getByRole("button", { name: "Block Grace Achieng" }),
  ).toBeInTheDocument();
});

it("shows Everything for someone holding every right, and the sign-in statuses as chips", async () => {
  fake.on(PEOPLE, [
    200,
    peoplePage([
      personFixture({
        id: "p-owner",
        firstName: "Antony",
        lastName: "Maina",
        everything: true,
        status: "active",
      }),
      personFixture({
        id: "p-new",
        firstName: "Mercy",
        lastName: "Achieng",
        status: "not_signed_in",
        modules: [],
      }),
      personFixture({
        id: "p-locked",
        firstName: "Peter",
        lastName: "Otieno",
        status: "locked",
        modules: [],
      }),
      personFixture({
        id: "p-blocked",
        firstName: "Daniel",
        lastName: "Kiprop",
        status: "blocked",
        active: false,
        modules: [],
      }),
    ]),
  ]);
  open();
  expect(await screen.findByText("Everything")).toHaveClass("mchip");
  expect(screen.getByText("Not signed in yet")).toHaveClass("chip", "wait");
  expect(screen.getByText("Locked")).toHaveClass("chip", "bad");
  expect(screen.getByText("Blocked")).toHaveClass("chip", "bad");
  expect(
    screen.getByRole("button", { name: "Unblock Daniel Kiprop" }),
  ).toBeInTheDocument();
});

it("offers no Edit, Block or New person without the rights", async () => {
  fake.on(PEOPLE, [200, peoplePage([grace()])]);
  open(["people.view"]);
  const row = await screen.findByRole("row", { name: /Grace Achieng/ });
  expect(
    screen.queryByRole("button", { name: "New person" }),
  ).not.toBeInTheDocument();
  expect(
    within(row).queryByRole("button", { name: /^Block/ }),
  ).not.toBeInTheDocument();
  expect(
    within(row).getByRole("button", { name: "View Grace Achieng" }),
  ).toBeInTheDocument();
});

it("blocks a person with a reason, and unblocks without one", async () => {
  fake.on(PEOPLE, [200, peoplePage([grace()])]);
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "Block Grace Achieng" }),
  );
  const dialog = await screen.findByRole("dialog", { name: "Block person" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Block" }));
  expect(
    await within(dialog).findByText("Enter the reason."),
  ).toBeInTheDocument();
  fireEvent.change(within(dialog).getByLabelText("Reason"), {
    target: { value: "Left the company" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Block" }));
  await waitFor(() =>
    expect(fake.sent("POST setup/people/person-2/deactivate")).toEqual([
      { version: 3, reason: "Left the company" },
    ]),
  );
});

it("opens the person pop up on Details with a side menu, and saves a new person on 7 days back", async () => {
  await openNewPerson();
  const rail = screen.getByRole("navigation", { name: "Sections" });
  expect(
    within(rail)
      .getAllByRole("button")
      .map((button) => button.textContent),
  ).toEqual([
    "Details",
    "Vehicles and dates0 vehicles · 7 days back",
    "Sign inNot signed in yet",
    "Access2 of 6",
    "Revenue2 of 3",
    "Petty cashOff",
  ]);
  // A new person has no PIN until they set it at first sign in.
  pane("Sign in");
  expect(
    screen.getByText("Not signed in yet", { selector: ".chip" }),
  ).toBeInTheDocument();
  pane("Vehicles and dates");
  expect(screen.getByLabelText("All vehicles")).not.toBeChecked();
  expect(screen.getByLabelText("Limit")).toHaveValue("days");
  expect(screen.getByLabelText("Days")).toHaveValue("7");
  expect(screen.getByText("Today, from 5 Oct 2026")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(fake.sent("POST setup/people")).toHaveLength(1));
  expect(fake.sent("POST setup/people")[0]).toMatchObject({
    firstName: "Jane",
    lastName: "Njeri",
    role: "Revenue clerk",
    scopeMode: "vehicles",
    vehicleIds: ["vehicle-1"],
    permissions: ["revenue.view", "revenue.capture"],
    backLimit: { mode: "days", count: 7, from: null },
  });
  expect(
    await screen.findByText("Saved. Jane sets a PIN at first sign in."),
  ).toBeInTheDocument();
});

it("opens the pane that holds the problem when a save is refused on screen", async () => {
  await openNewPerson();
  pane("Vehicles and dates");
  fireEvent.change(screen.getByLabelText("Limit"), {
    target: { value: "months" },
  });
  fireEvent.change(screen.getByLabelText("Months"), { target: { value: "" } });
  pane("Access");
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByText("Enter the number of months.")).toBeVisible();
  expect(screen.getByLabelText("Months")).toBeVisible();
  expect(fake.sent("POST setup/people")).toHaveLength(0);
});

it("ticks what a right needs and the whole module at once, and shows the petty cash sections", async () => {
  await openNewPerson();
  pane("Access");
  const card = screen
    .getByText("Petty cash", { selector: ".pg b" })
    .closest(".pg") as HTMLElement;
  expect(card).toHaveClass("wide");
  expect(
    within(card).getAllByText(/^(View|Expenses|Approval)$/, {
      selector: ".pt",
    }),
  ).toHaveLength(3);
  fireEvent.click(within(card).getByLabelText("Approve an expense"));
  expect(within(card).getByLabelText("View petty cash")).toBeChecked();
  fireEvent.click(within(card).getByLabelText("All of Petty cash"));
  expect(within(card).getByLabelText("Add an expense")).toBeChecked();
  const rail = screen.getByRole("navigation", { name: "Sections" });
  expect(
    within(rail).getByRole("button", { name: /^Petty cash/ }),
  ).toHaveTextContent("All");
  fireEvent.click(within(card).getByLabelText("View petty cash"));
  expect(within(card).getByLabelText("Approve an expense")).not.toBeChecked();
  expect(
    within(rail).getByRole("button", { name: /^Petty cash/ }),
  ).toHaveTextContent("Off");
});

it("ties Holds a float to the right to add petty cash expenses", async () => {
  await openNewPerson();
  fireEvent.click(screen.getByLabelText("Holds a float"));
  pane("Access");
  expect(screen.getByLabelText("Add an expense")).toBeChecked();
  expect(screen.getByLabelText("View petty cash")).toBeChecked();
});

it("shows a person's sign in, and acts at once on reset, a device, and Remove all", async () => {
  fake.on(PEOPLE, [200, peoplePage([grace()])]);
  fake.on("setup/people/person-2", [
    200,
    {
      ...grace(),
      signIn: {
        status: "active",
        lock: null,
        lastSignedInAt: "2026-10-09T08:40:00Z",
        email: "grace@example.com",
        devices: [
          {
            id: "dev-1",
            name: "Edge on Windows",
            trustedAt: "2026-09-08T10:00:00Z",
            lastUsedAt: "2026-10-09T08:40:00Z",
          },
          {
            id: "dev-2",
            name: "XCODE app on Tecno Spark 20",
            trustedAt: "2026-09-09T10:00:00Z",
            lastUsedAt: "2026-10-09T06:31:00Z",
          },
        ],
      },
    },
  ]);
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Grace Achieng" }),
  );
  pane("Sign in");
  expect(await screen.findByText("grace@example.com")).toBeInTheDocument();
  expect(screen.getByText("Edge on Windows")).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Remove XCODE app on Tecno Spark 20" }),
  );
  await waitFor(() =>
    expect(
      lastPost("setup/people/person-2/trusted-devices/dev-2/remove"),
    ).toBeTruthy(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Remove all" }));
  await waitFor(() =>
    expect(lastPost("setup/people/person-2/sign-out")).toBeTruthy(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Make Grace reset the PIN" }),
  );
  await waitFor(() =>
    expect(lastPost("setup/people/person-2/pin-reset")).toBeTruthy(),
  );
  // None of these waited for Save.
  expect(fake.calls.filter((call) => call.method === "PUT")).toHaveLength(0);
});

it("offers no sign-in actions without the right", async () => {
  fake.on(PEOPLE, [200, peoplePage([grace()])]);
  fake.on("setup/people/person-2", [
    200,
    {
      ...grace(),
      signIn: {
        status: "active",
        lock: null,
        lastSignedInAt: null,
        email: "grace@example.com",
        devices: [
          {
            id: "dev-1",
            name: "Edge on Windows",
            trustedAt: "2026-09-08T10:00:00Z",
            lastUsedAt: null,
          },
        ],
      },
    },
  ]);
  open(["people.view", "people.edit"]);
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Grace Achieng" }),
  );
  pane("Sign in");
  expect(await screen.findByText("Edge on Windows")).toBeInTheDocument();
  expect(screen.getByText("Never")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /reset the PIN/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /^Remove/ }),
  ).not.toBeInTheDocument();
});

it("says why the server refused to save a person, and keeps the edit with the version it was based on", async () => {
  fake.on(PEOPLE, [200, peoplePage([grace()])]);
  fake.on("setup/people/person-2", [200, grace()]);
  fake.on(
    "PUT setup/people/person-2",
    problem(409, "Conflict", "Someone else saved this person first."),
  );
  open();
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Grace Achieng" }),
  );
  fireEvent.change(await screen.findByLabelText("First name"), {
    target: { value: "Gracie" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(
    await screen.findByText("Someone else saved this person first."),
  ).toBeInTheDocument();
  expect(fake.sent("PUT setup/people/person-2")[0]).toMatchObject({
    firstName: "Gracie",
    version: 3,
    backLimit: { mode: "months", count: 1, from: "2026-09-14" },
  });
});
