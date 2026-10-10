import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { presetPeriod, type Period } from "@xcode/shared/periods";

import { PeriodPicker } from "../components/period/PeriodPicker";

const TODAY = "2026-10-09";

function Harness({
  start = presetPeriod("thisWeek", TODAY, 1),
  onChange = () => {},
}: {
  start?: Period;
  onChange?: (period: Period) => void;
}) {
  const [period, setPeriod] = useState(start);
  return (
    <>
      <PeriodPicker
        period={period}
        businessDate={TODAY}
        firstDayOfWeek={1}
        onChange={(next) => {
          onChange(next);
          setPeriod(next);
        }}
      />
      <button>elsewhere</button>
    </>
  );
}

const changeTo = (element: HTMLElement, value: string) =>
  fireEvent.change(element, { target: { value } });

const trigger = () => screen.getByRole("button", { name: /^Period, / });
const open = () => {
  fireEvent.click(trigger());
  return screen.getByRole("dialog", { name: "Choose a period" });
};

it("names the period by its day, or by its first and last day", () => {
  const { unmount } = render(<Harness />);
  expect(trigger()).toHaveTextContent("5 to 11 Oct 2026");
  unmount();
  render(<Harness start={presetPeriod("today", TODAY, 1)} />);
  expect(trigger()).toHaveTextContent("Fri 9 Oct 2026");
});

it("keeps the panel closed until the period is pressed, and does not show the dates inline", () => {
  render(<Harness />);
  expect(trigger()).toHaveAttribute("aria-expanded", "false");
  expect(trigger()).toHaveAttribute("aria-haspopup", "dialog");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("From")).not.toBeInTheDocument();
  const panel = open();
  expect(trigger()).toHaveAttribute("aria-expanded", "true");
  expect(trigger().getAttribute("aria-controls")).toBe(panel.id);
  expect(within(panel).getByLabelText("From")).toBeInTheDocument();
  expect(within(panel).getByLabelText("To")).toBeInTheDocument();
});

it("steps back and forward with the arrows beside it, and cannot go past the business date", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Previous week" }));
  expect(onChange).toHaveBeenLastCalledWith({
    from: "2026-09-28",
    to: "2026-10-04",
    unit: "week",
  });
  expect(trigger()).toHaveTextContent("28 Sep to 4 Oct 2026");

  fireEvent.click(screen.getByRole("button", { name: "Next week" }));
  expect(trigger()).toHaveTextContent("5 to 11 Oct 2026");
  expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();
});

it("calls a step by what it steps over", () => {
  render(<Harness start={presetPeriod("lastMonth", TODAY, 1)} />);
  fireEvent.click(screen.getByRole("button", { name: "Previous month" }));
  expect(trigger()).toHaveTextContent("1 to 31 Aug 2026");
});

it("lists the presets in the panel, marks the current one and applies the one chosen", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  const panel = open();
  expect(
    within(panel)
      .getAllByRole("menuitemradio")
      .map((item) => item.textContent),
  ).toEqual([
    "Today",
    "Yesterday",
    "This week",
    "Last week",
    "Last 4 weeks",
    "This month",
    "Last month",
  ]);
  expect(
    within(panel).getByRole("menuitemradio", { name: "This week" }),
  ).toHaveAttribute("aria-checked", "true");
  fireEvent.click(
    within(panel).getByRole("menuitemradio", { name: "Last 4 weeks" }),
  );
  expect(onChange).toHaveBeenLastCalledWith({
    from: "2026-09-07",
    to: "2026-10-04",
    unit: "fourWeeks",
  });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger()).toHaveTextContent("7 Sep to 4 Oct 2026");
});

it("marks no preset when stepping lands on none of them", () => {
  render(<Harness start={presetPeriod("today", TODAY, 1)} />);
  fireEvent.click(screen.getByRole("button", { name: "Previous day" }));
  fireEvent.click(screen.getByRole("button", { name: "Previous day" }));
  const panel = open();
  expect(
    within(panel)
      .getAllByRole("menuitemradio")
      .some((item) => item.getAttribute("aria-checked") === "true"),
  ).toBe(false);
});

it("takes two days of its own under Custom dates and closes on Show these dates", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  const panel = open();
  expect(within(panel).getByText("Custom dates")).toBeInTheDocument();
  expect(within(panel).getByLabelText("From")).toHaveValue("2026-10-05");
  expect(within(panel).getByLabelText("To")).toHaveValue("2026-10-11");

  changeTo(within(panel).getByLabelText("From"), "2026-09-01");
  changeTo(within(panel).getByLabelText("To"), "2026-09-20");
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.click(
    within(panel).getByRole("button", { name: "Show these dates" }),
  );
  expect(onChange).toHaveBeenCalledWith({
    from: "2026-09-01",
    to: "2026-09-20",
    unit: "custom",
  });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger()).toHaveTextContent("1 to 20 Sep 2026");

  fireEvent.click(screen.getByRole("button", { name: "Next period" }));
  expect(onChange).toHaveBeenLastCalledWith({
    from: "2026-09-21",
    to: "2026-10-10",
    unit: "custom",
  });
});

it.each([
  ["", "2026-10-02", "Enter both dates."],
  ["2026-10-05", "2026-10-02", "From cannot be after To."],
  ["2026-10-05", "2026-10-10", "The dates cannot be after today."],
  ["2025-09-01", "2026-09-30", "A period can cover at most 367 days."],
])("refuses %j to %j inside the panel with a message", (from, to, message) => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  const panel = open();
  changeTo(within(panel).getByLabelText("From"), from);
  changeTo(within(panel).getByLabelText("To"), to);
  fireEvent.click(
    within(panel).getByRole("button", { name: "Show these dates" }),
  );
  expect(within(panel).getByText(message)).toBeInTheDocument();
  expect(within(panel).getByLabelText("From")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

it("accepts a span of exactly 367 days", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  const panel = open();
  changeTo(within(panel).getByLabelText("From"), "2025-10-08");
  changeTo(within(panel).getByLabelText("To"), "2026-10-09");
  fireEvent.click(
    within(panel).getByRole("button", { name: "Show these dates" }),
  );
  expect(onChange).toHaveBeenCalledWith({
    from: "2025-10-08",
    to: "2026-10-09",
    unit: "custom",
  });
});

it("closes on Escape and puts focus back on the period", () => {
  render(<Harness />);
  open();
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger()).toHaveFocus();
});

it("closes on a press outside it, and not on a press inside", () => {
  render(<Harness />);
  const panel = open();
  fireEvent.mouseDown(within(panel).getByText("Custom dates"));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.mouseDown(screen.getByRole("button", { name: "elsewhere" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("closes when the period is pressed again, and puts focus on the first preset when it opens", () => {
  render(<Harness start={presetPeriod("today", TODAY, 1)} />);
  const panel = open();
  expect(
    within(panel).getByRole("menuitemradio", { name: "Today" }),
  ).toHaveFocus();
  fireEvent.click(trigger());
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
