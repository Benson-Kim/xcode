import { fireEvent, screen } from "@testing-library/react-native";

import { catalog, fakeApi, people, tokens } from "./fakeApi";
import { startApp, trustPhone, typePin } from "./helpers";

async function openDeleteAccount() {
  await trustPhone();
  const api = fakeApi();
  api.on("auth/pin", [200, tokens(2)]);
  api.on("auth/session", [200, people.owner]);
  api.on("setup/access/catalog", [200, catalog]);
  await startApp();
  await screen.findByText("Welcome back, Antony");
  await typePin("4826");
  await screen.findByText("Hi Antony");
  await fireEvent.press(screen.getByRole("tab", { name: "More" }));
  await fireEvent.press(await screen.findByText("Delete my account"));
  await screen.findByLabelText("Your PIN");
  return api;
}

it("asks for the account to be deleted once the server confirms the PIN", async () => {
  const api = await openDeleteAccount();
  api.on("auth/pin", [200, tokens(5)]);
  api.on("setup/me/deletion-request", [202, {}]);
  await typePin("4826");
  await screen.findByText("Request sent");
  expect(api.sent("auth/pin")).toHaveLength(2);
  expect(api.sent("auth/pin")[1]).toMatchObject({
    phoneNumber: "0733520614",
    pin: "4826",
  });
  expect(
    api.calls.find(({ path }) => path === "setup/me/deletion-request"),
  ).toMatchObject({
    method: "POST",
    headers: expect.objectContaining({ Authorization: "Bearer access-5" }),
  });
  await fireEvent.press(screen.getByText("Done"));
  await screen.findByText("Switch user");
});

it("says how many tries are left after a wrong PIN and asks nothing", async () => {
  const api = await openDeleteAccount();
  api.on("auth/pin", [401, { status: "authentication_failed", triesLeft: 3 }]);
  await typePin("1111");
  await screen.findByText("Wrong PIN. 3 tries left.");
  expect(screen.getByLabelText("0 of 4 numbers entered")).toBeTruthy();
  expect(api.sent("setup/me/deletion-request")).toEqual([]);
});

it("says that asking needs network", async () => {
  const api = await openDeleteAccount();
  api.on("auth/pin", "offline");
  await typePin("4826");
  await screen.findByText(
    "No internet. Asking to delete your account needs network.",
  );
  expect(api.sent("setup/me/deletion-request")).toEqual([]);
});

it("goes back to More on Cancel", async () => {
  await openDeleteAccount();
  await fireEvent.press(screen.getByText("Cancel"));
  await screen.findByText("Switch user");
});
