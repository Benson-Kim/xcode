import { act, fireEvent, render, screen } from "@testing-library/react-native";

import { CaptureSheet } from "../src/shell/revenue/CaptureSheet";
import type { Target } from "../src/shell/revenue/model";

const target: Target = {
  vehicle: {
    id: "v-1",
    companyId: "company-1",
    companyName: "North Star",
    registration: "KDA 482M",
    joinedOn: "2026-01-01",
    leftOn: null,
    earliestMissing: "2026-09-28",
    days: [],
    totalAmount: 0,
    totalExpected: 0,
    percent: null,
  },
  date: "2026-09-29",
  earlier: "2026-09-28",
};

it("keeps the sheet open while its save runs, so the save's answer is never lost", async () => {
  let finish: (failure?: Error) => void = () => {};
  const onSave = jest.fn(
    () =>
      new Promise<void>((resolve, reject) => {
        finish = (failure) => (failure ? reject(failure) : resolve());
      }),
  );
  const onClose = jest.fn();
  const onOpenGap = jest.fn();
  await render(
    <CaptureSheet
      target={target}
      canReason={false}
      onSave={onSave}
      onClose={onClose}
      onOpenGap={onOpenGap}
    />,
  );
  await fireEvent.changeText(screen.getByLabelText("Revenue amount"), "1500");
  await fireEvent.press(screen.getByRole("button", { name: "Save" }));
  expect(onSave).toHaveBeenCalledTimes(1);

  const close = screen.getByRole("button", { name: "Close" });
  const gap = screen.getByRole("button", { name: /^Open / });
  expect(close).toBeDisabled();
  expect(gap).toBeDisabled();
  await fireEvent.press(close);
  await fireEvent.press(gap);
  expect(onClose).not.toHaveBeenCalled();
  expect(onOpenGap).not.toHaveBeenCalled();

  await act(async () => finish(new Error("The phone is out of space.")));
  expect(screen.getByText("The phone is out of space.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Close" })).not.toBeDisabled();
  await fireEvent.press(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});
