import { fireEvent, render, screen } from "@testing-library/react-native";

import type { RevenueCell } from "@xcode/shared/revenue";

import { CaptureSheet } from "../src/shell/revenue/CaptureSheet";
import type { Target } from "../src/shell/revenue/model";
import { TargetsContext } from "../src/shell/targets";

// This vehicle's low figure on the day is KES 3,000; the fuel question comes from KES 10,000.
const cell: RevenueCell = {
  date: "2026-09-29",
  status: "missing",
  expected: 5000,
  lowBelow: 3000,
  amount: null,
  reason: null,
  note: null,
  canEdit: true,
  editedAfterCapture: false,
  version: null,
};

const target = (day: Partial<RevenueCell> = {}): Target => ({
  vehicle: {
    id: "v-1",
    companyId: "company-1",
    companyName: "North Star",
    registration: "KDA 482M",
    joinedOn: "2026-01-01",
    leftOn: null,
    earliestMissing: null,
    days: [],
    totalAmount: 0,
    totalExpected: 0,
    percent: null,
  },
  date: "2026-09-29",
  cell: { ...cell, ...day },
  earlier: null,
});

async function open(
  options: { day?: Partial<RevenueCell>; canReason?: boolean } = {},
  targets = true,
) {
  const onSave = jest.fn(async () => {});
  await render(
    <TargetsContext.Provider value={targets}>
      <CaptureSheet
        target={target(options.day)}
        canReason={options.canReason ?? false}
        fuelQuestionFrom={10000}
        onSave={onSave}
        onClose={() => {}}
        onOpenGap={() => {}}
      />
    </TargetsContext.Provider>,
  );
  return onSave;
}

const type = (text: string) =>
  fireEvent.changeText(screen.getByLabelText("Revenue amount"), text);
const tap = (role: "radio" | "checkbox", name: string) =>
  fireEvent.press(screen.getByRole(role, { name }));
const save = () =>
  fireEvent.press(screen.getByRole("button", { name: "Save" }));

it("asks a reason below the vehicle's own low figure, even without the no-earnings right, then offers Not fueled", async () => {
  const onSave = await open();

  await type("2000");
  expect(screen.getByText("Revenue is below KES 3,000.")).toBeTruthy();
  expect(screen.queryByRole("radio", { name: "Yes" })).toBeNull();
  await save();
  expect(
    screen.getByText("Choose the reason. Revenue is below KES 3,000."),
  ).toBeTruthy();
  expect(onSave).not.toHaveBeenCalled();

  await tap("radio", "Garage");
  await tap("checkbox", "Not fueled");
  await save();
  expect(onSave).toHaveBeenCalledWith({
    amount: 2000,
    reason: "Garage",
    note: null,
    fuel: "no",
  });
});

it("offers only the Not fueled tag from the low figure up to the fuel question, with no reasons", async () => {
  const onSave = await open({ canReason: true });

  await type("3000");
  expect(screen.getByText("Tag")).toBeTruthy();
  expect(screen.queryByRole("radio", { name: "Garage" })).toBeNull();
  expect(screen.queryByRole("radio", { name: "Yes" })).toBeNull();
  await save();
  expect(onSave).toHaveBeenLastCalledWith({
    amount: 3000,
    reason: null,
    note: null,
    fuel: null,
  });

  await tap("checkbox", "Not fueled");
  await save();
  expect(onSave).toHaveBeenLastCalledWith({
    amount: 3000,
    reason: null,
    note: null,
    fuel: "no",
  });
});

it("asks Fueled? from the fuel question amount, clears an answer tapped again, drops Yes and keeps No below it", async () => {
  const onSave = await open();

  await type("12000");
  expect(screen.getByText("Fueled?")).toBeTruthy();
  expect(screen.getByRole("radio", { name: "No" })).toBeTruthy();
  expect(screen.queryByRole("checkbox", { name: "Not fueled" })).toBeNull();
  await tap("radio", "Yes");
  await tap("radio", "Yes");
  await save();
  expect(onSave).toHaveBeenLastCalledWith({
    amount: 12000,
    reason: null,
    note: null,
    fuel: null,
  });

  await tap("radio", "Yes");
  await type("9000");
  expect(
    screen.getByRole("checkbox", { name: "Not fueled" }).props
      .accessibilityState,
  ).toMatchObject({ checked: false });
  await type("12000");
  await tap("radio", "No");
  await type("9000");
  expect(
    screen.getByRole("checkbox", { name: "Not fueled" }).props
      .accessibilityState,
  ).toMatchObject({ checked: true });
  await save();
  expect(onSave).toHaveBeenLastCalledWith({
    amount: 9000,
    reason: null,
    note: null,
    fuel: "no",
  });
});

it("sends no fuel answer for a day with no revenue", async () => {
  const onSave = await open({ canReason: true });

  await tap("radio", "Garage");
  await save();
  expect(onSave).toHaveBeenCalledWith({
    amount: null,
    reason: "Garage",
    note: null,
  });
});

it("opens a saved day with its fuel answer", async () => {
  const onSave = await open({
    day: { status: "amount", amount: 15000, fuel: "yes", version: 2 },
  });

  expect(
    screen.getByRole("radio", { name: "Yes" }).props.accessibilityState,
  ).toMatchObject({ checked: true });
  await save();
  expect(onSave).toHaveBeenCalledWith({
    amount: 15000,
    reason: null,
    note: null,
    fuel: "yes",
  });
});

it("shows the day's expected figure only while Targets is on", async () => {
  await open({}, true);
  expect(screen.getByText("Tue 29 Sep 2026. Expected KES 5,000")).toBeTruthy();

  await open({}, false);
  expect(screen.getByText("Tue 29 Sep 2026")).toBeTruthy();
  expect(screen.queryByText(/Expected/)).toBeNull();
});
