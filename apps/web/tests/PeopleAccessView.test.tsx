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

let fake: ReturnType<typeof fakeApi>;
beforeEach(() => {
  fake = fakeApi();
  fake.on(PEOPLE, [200, peoplePage([])]);
  fake.on("setup/access/catalog", [200, catalogFixture]);
  fake.on("setup/access/roles", [200, rolesFixture]);
  fake.on("setup/access/scope-options", [200, scopeOptionsFixture]);
  fake.on("POST setup/people", [200, { id: "person-1" }]);
  fake.on("POST setup/people/*", [200, { ok: true }]);
});

async function openNewPerson(canManageAccess: boolean) {
  renderInApp(<PeopleAccessView canManageAccess={canManageAccess} />, {
    role: "Office admin",
    permissions: canManageAccess
      ? [
          "people.view",
          "people.manage",
          "access.manage",
          "revenue.view",
          "revenue.capture",
        ]
      : ["people.view", "people.manage", "revenue.view", "revenue.capture"],
  });
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

it("limits a person to chosen vehicles and sends the role's own defaults", async () => {
  await openNewPerson(false);

  expect(screen.getByLabelText("Capture revenue")).toBeChecked();
  expect(screen.getByLabelText("View reports")).not.toBeChecked();
  expect(screen.getByLabelText("View reports")).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  const alerts = screen.getAllByRole("alert");
  expect(alerts).toHaveLength(2);
  expect(alerts[0]).toHaveTextContent("Fix the highlighted field to save.");
  expect(alerts[1]).toHaveTextContent("Tick at least one vehicle.");
  expect(fetch).not.toHaveBeenCalledWith(
    "/api/setup/people",
    expect.objectContaining({ method: "POST" }),
  );

  fireEvent.click(await screen.findByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/setup/people",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  const post = fake.sent("POST setup/people")[0];
  expect(post).toMatchObject({
    scopeMode: "vehicles",
    vehicleIds: ["vehicle-1"],
    companyIds: [],
    permissions: ["revenue.view", "revenue.capture"],
  });
});

it("does not silently truncate an overlong phone number when adding a person", async () => {
  await openNewPerson(false);
  fireEvent.change(screen.getByLabelText("Mobile number"), {
    target: { value: "07110000012" },
  });
  fireEvent.click(await screen.findByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(
    screen.getByText("Enter all 10 numbers, starting 07 or 01."),
  ).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalledWith(
    "/api/setup/people",
    expect.objectContaining({ method: "POST" }),
  );
});

it("ticking a permission ticks what it needs, wherever it sits in the catalogue", async () => {
  await openNewPerson(true);

  // Unticking the one it needs takes the dependent with it, and says so.
  fireEvent.click(screen.getByLabelText("View revenue records"));
  expect(screen.getByLabelText("Capture revenue")).not.toBeChecked();
  expect(
    screen.getByText(/Also unticked, because it needs this: Capture revenue/),
  ).toBeInTheDocument();

  // Ticking the dependent again brings back what it needs. "Capture revenue" is not the first permission in
  // the catalogue, which is the case that used to be missed.
  fireEvent.click(screen.getByLabelText("Capture revenue"));
  expect(screen.getByLabelText("View revenue records")).toBeChecked();
  expect(
    screen.getByText(/Also ticked, because it is needed: View revenue records/),
  ).toBeInTheDocument();

  fireEvent.click(await screen.findByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/setup/people",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  const post = fake.sent("POST setup/people")[0];
  expect(post.permissions).toEqual(
    expect.arrayContaining(["revenue.view", "revenue.capture"]),
  );
});

it("offers companies when the scope is chosen companies", async () => {
  await openNewPerson(true);
  fireEvent.click(screen.getByRole("radio", { name: "Chosen companies" }));
  fireEvent.click(await screen.findByLabelText("North Star"));
  fireEvent.click(screen.getByLabelText("View reports"));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/setup/people",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  const post = fake.sent("POST setup/people")[0];
  expect(post).toMatchObject({
    scopeMode: "companies",
    companyIds: ["company-1"],
    vehicleIds: [],
    permissions: expect.arrayContaining(["reports.view"]),
  });
});

it("says why the server refused to save a person", async () => {
  const detail =
    "You can only give access to the companies you can see yourself.";
  fake.on(
    "POST setup/people",
    problem(403, "Not permitted in this organization or data scope.", detail),
  );
  await openNewPerson(false);
  fireEvent.click(await screen.findByLabelText("KDA 482M"));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(detail);
  expect(
    screen.queryByText("Not permitted in this organization or data scope."),
  ).not.toBeInTheDocument();
});

it("asks for the reason beside its field before removing someone's access", async () => {
  const fetcher = fake.fetch;
  fake.on(PEOPLE, [200, peoplePage([personFixture()])]);
  renderInApp(<PeopleAccessView canManageAccess />, {
    role: "Owner",
    permissions: ["people.view", "people.manage", "access.manage"],
  });
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Grace Achieng" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Remove access" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm removal" }));

  expect(screen.getByRole("alert")).toHaveTextContent(
    "Give a reason for removing access.",
  );
  expect(screen.getByLabelText("Reason")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(fetcher).not.toHaveBeenCalledWith(
    "/api/setup/people/person-2/deactivate",
    expect.anything(),
  );

  fireEvent.change(screen.getByLabelText("Reason"), {
    target: { value: "Left the SACCO" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm removal" }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/setup/people/person-2/deactivate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ version: 3, reason: "Left the SACCO" }),
      }),
    ),
  );
});

it("filters the list by role and by where each person is with signing in", async () => {
  const person = (
    id: string,
    firstName: string,
    role: string,
    extra: object,
  ) => ({
    id,
    firstName,
    lastName: "Test",
    email: `${id}@example.com`,
    phoneNumber: "+254711000000",
    role,
    active: true,
    scopeMode: "all",
    companyIds: [],
    vehicleIds: [],
    permissions: [],
    hasPin: true,
    version: 1,
    ...extra,
  });
  const people = [
    person("a", "Amina", "Revenue clerk", {}),
    person("b", "Baraka", "Owner", { hasPin: false }),
    person("c", "Chebet", "Revenue clerk", { active: false }),
  ];
  // The server filters: active has a PIN, waiting has none yet, none is switched off.
  const state = (x: (typeof people)[number]) =>
    !x.active ? "none" : x.hasPin ? "active" : "waiting";
  const filtered = (sent: Sent) => {
    const query = new URL(sent.path, "http://localhost").searchParams;
    const role = query.get("role");
    const status = query.get("status");
    return [
      200,
      peoplePage(
        people.filter(
          (x) => (!role || x.role === role) && (!status || state(x) === status),
        ),
      ),
    ] as const;
  };
  fake.on(PEOPLE, filtered);
  fake.on("setup/people?*", filtered);
  renderInApp(<PeopleAccessView />, { permissions: ["people.view"] });
  expect(await screen.findByText("3 people")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Sign in"), {
    target: { value: "waiting" },
  });
  expect(await screen.findByText("1 person")).toBeInTheDocument();
  expect(
    await screen.findByRole("button", { name: "View Baraka Test" }),
  ).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Sign in"), {
    target: { value: "all" },
  });
  fireEvent.change(screen.getByLabelText("Role"), {
    target: { value: "Revenue clerk" },
  });
  expect(await screen.findByText("2 people")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "View Baraka Test" }),
  ).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Sign in"), {
    target: { value: "none" },
  });
  expect(
    await screen.findByRole("button", { name: "View Chebet Test" }),
  ).toBeInTheDocument();
  expect(
    fake.calls.filter((call) => call.path.startsWith("setup/people?")).at(-1)
      ?.path,
  ).toBe("setup/people?role=Revenue+clerk&status=none&page=1&pageSize=25");
  expect(
    screen.queryByRole("button", { name: "View Amina Test" }),
  ).not.toBeInTheDocument();
});

it("offers only roles whose defaults the editor can grant", async () => {
  fake.on("setup/access/roles", [
    200,
    [
      ...rolesFixture,
      { id: "role-3", name: "People viewer", permissions: ["people.view"] },
    ],
  ]);
  renderInApp(<PeopleAccessView canManageAccess />, {
    role: "Office admin",
    permissions: ["people.view", "people.manage", "access.manage"],
  });
  fireEvent.click(await screen.findByRole("button", { name: "New person" }));

  // The list's own Role filter stays behind the pop up and offers every role.
  const editor = within(screen.getByRole("dialog", { name: "New person" }));
  const rolePicker = await editor.findByRole("combobox", { name: "Role" });
  await waitFor(() => expect(rolePicker).toHaveValue("People viewer"));
  expect(
    editor.queryByRole("option", { name: "Revenue clerk" }),
  ).not.toBeInTheDocument();
  expect(
    editor.queryByRole("option", { name: "Fleet manager" }),
  ).not.toBeInTheDocument();
  expect(
    editor.getByRole("option", { name: "People viewer" }),
  ).toBeInTheDocument();
});

it("includes hidden companies and vehicles in each person's scope summary", async () => {
  fake.on(PEOPLE, [
    200,
    {
      items: [
        {
          id: "person-1",
          firstName: "Alex",
          lastName: "Kim",
          email: "alex@example.com",
          phoneNumber: "0711000001",
          role: "Revenue clerk",
          active: true,
          scopeMode: "companies",
          companyIds: [],
          vehicleIds: [],
          otherCompanies: 2,
          otherVehicles: 0,
          permissions: [],
          hasPin: true,
          version: 1,
        },
        {
          id: "person-2",
          firstName: "Sam",
          lastName: "Lee",
          email: "sam@example.com",
          phoneNumber: "0711000002",
          role: "Revenue clerk",
          active: true,
          scopeMode: "vehicles",
          companyIds: [],
          vehicleIds: ["vehicle-1"],
          otherCompanies: 0,
          otherVehicles: 1,
          permissions: [],
          hasPin: true,
          version: 1,
        },
      ],
      pageNumber: 1,
      pageSize: 25,
      total: 2,
    },
  ]);

  renderInApp(<PeopleAccessView />, {
    permissions: ["people.view"],
  });

  expect(await screen.findByText("2 companies (2 hidden)")).toBeInTheDocument();
  expect(screen.getByText("2 vehicles (1 hidden)")).toBeInTheDocument();
});

const STALE = "Settings changed. Reload before saving.";

async function openGrace() {
  fake.on(PEOPLE, [200, peoplePage([personFixture()])]);
  renderInApp(<PeopleAccessView canManageAccess />, {
    role: "Owner",
    permissions: ["people.view", "people.manage", "access.manage"],
  });
  fireEvent.click(
    await screen.findByRole("button", { name: "Edit Grace Achieng" }),
  );
  const save = screen.getByRole("button", { name: "Save" });
  await waitFor(() => expect(save).toBeEnabled());
  return save;
}

it("keeps the edit and sends the version it was based on when someone else saved first", async () => {
  const save = await openGrace();
  fake.on("PUT setup/people/person-2", problem(409, STALE));
  const first = screen.getByLabelText("First name");
  fireEvent.change(first, { target: { value: "Gracie" } });
  fireEvent.click(save);

  expect(await screen.findByRole("alert")).toHaveTextContent(STALE);
  expect(first).toHaveValue("Gracie");
  expect(save).toBeEnabled();
  expect(fake.sent("PUT setup/people/person-2")).toHaveLength(1);
  expect(fake.sent("PUT setup/people/person-2")[0].version).toBe(3);
  expect(screen.queryByText(/Changes saved for/)).not.toBeInTheDocument();
  expect(fake.sent(PEOPLE)).toHaveLength(1);
});

it("shows the server's reason when signing someone out everywhere is refused", async () => {
  await openGrace();
  const why = "You cannot sign out someone with more access than you.";
  fake.on(
    "POST setup/people/person-2/sign-out",
    problem(403, "Not permitted in this organization or data scope.", why),
  );
  const signOut = screen.getByRole("button", {
    name: "Sign out of all devices",
  });
  fireEvent.click(signOut);

  expect(await screen.findByRole("alert")).toHaveTextContent(why);
  expect(signOut).toBeEnabled();
  expect(
    screen.queryByText(/is signed out of every device/),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText("Not permitted in this organization or data scope."),
  ).not.toBeInTheDocument();
});

it.each([
  [
    "a passing outage at the proxy",
    [503, { status: "service_unavailable" }],
    "The request could not be completed.",
  ],
  [
    "no connection",
    "offline",
    "Unable to reach the server. Check your connection.",
  ],
] as const)(
  "keeps a new person's details when adding fails with %s, and adds them on the next try",
  async (_name, reply, message) => {
    fake.on("POST setup/people", reply);
    await openNewPerson(false);
    fireEvent.click(await screen.findByLabelText("KDA 482M"));
    const save = screen.getByRole("button", { name: "Save" });
    fireEvent.click(save);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByLabelText("First name")).toHaveValue("Jane");
    expect(screen.getByLabelText("Mobile number")).toHaveValue("0711000001");
    expect(screen.getByLabelText("KDA 482M")).toBeChecked();
    expect(save).toBeEnabled();
    expect(screen.queryByText(/added\. They sign in/)).not.toBeInTheDocument();
    expect(fake.sent("POST setup/people")).toHaveLength(1);

    fake.on("POST setup/people", [200, { id: "person-1" }]);
    fireEvent.click(save);
    await waitFor(() => expect(fake.sent("POST setup/people")).toHaveLength(2));
    expect(fake.sent("POST setup/people")[1]).toMatchObject({
      firstName: "Jane",
      vehicleIds: ["vehicle-1"],
    });
    expect(
      await screen.findByText(/Jane Njeri added\. They sign in/),
    ).toBeInTheDocument();
  },
);
