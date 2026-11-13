import { fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { Field, SearchSelect, type SearchOption } from "../components/ui";
import { listboxOf, nameOf, optionsOf, pick } from "./searchSelect";

type RankVector = {
  name: string;
  query: string;
  options: (string | { label: string; group?: string })[];
  expected: string[];
};

const RANK_VECTORS = JSON.parse(
  readFileSync(
    join(
      __dirname,
      "../../../packages/shared/tests/fixtures/rank-options.json",
    ),
    "utf8",
  ),
) as RankVector[];

const OPTIONS: SearchOption[] = [
  { value: "v1", label: "KDA 482M, Rongai Express" },
  { value: "v2", label: "KDB 100X, Rongai Express" },
  { value: "v3", label: "KDC 200Y, Metro Trans" },
];

function Harness({
  start = "",
  onChange = () => {},
  options = OPTIONS,
}: {
  start?: string;
  onChange?: (value: string) => void;
  options?: SearchOption[];
}) {
  const [value, setValue] = useState(start);
  return (
    <>
      <SearchSelect
        aria-label="Vehicle"
        placeholder="Choose the vehicle"
        options={options}
        value={value}
        onChange={(next) => {
          onChange(next);
          setValue(next);
        }}
      />
      <button>after</button>
    </>
  );
}

const input = () => screen.getByRole("combobox", { name: "Vehicle" });
const names = () =>
  within(listboxOf(input()))
    .queryAllByRole("option")
    .map((option) => option.textContent);

it("is a combobox over a listbox, closed until it is used, showing the chosen label", () => {
  render(<Harness start="v2" />);
  expect(input()).toHaveAttribute("aria-expanded", "false");
  expect(input()).toHaveAttribute("aria-autocomplete", "list");
  expect(input()).toHaveValue("KDB 100X, Rongai Express");
  expect(screen.queryByRole("option", { name: /KDA/ })).not.toBeInTheDocument();
  expect(listboxOf(input())).toHaveAttribute("role", "listbox");
});

it("shows the placeholder when nothing is chosen", () => {
  render(<Harness />);
  expect(input()).toHaveValue("");
  expect(input()).toHaveAttribute("placeholder", "Choose the vehicle");
});

it("opens on focus with every option, marking the chosen one", () => {
  render(<Harness start="v2" />);
  fireEvent.focus(input());
  expect(input()).toHaveAttribute("aria-expanded", "true");
  expect(names()).toEqual(OPTIONS.map((option) => option.label));
  expect(screen.getByRole("option", { name: /KDB/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.getByRole("option", { name: /KDA/ })).toHaveAttribute(
    "aria-selected",
    "false",
  );
});

it("narrows the options as you type, every word having to match, in any case", () => {
  render(<Harness />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "metro" } });
  expect(names()).toEqual(["KDC 200Y, Metro Trans"]);
  fireEvent.change(input(), { target: { value: "rongai kdb" } });
  expect(names()).toEqual(["KDB 100X, Rongai Express"]);
  fireEvent.change(input(), { target: { value: "zzz" } });
  expect(names()).toEqual([]);
  expect(screen.getByText("Nothing matches")).toBeInTheDocument();
});

it("moves through the options with the arrow keys, naming the highlighted one in aria-activedescendant", () => {
  render(<Harness />);
  fireEvent.focus(input());
  const highlighted = () =>
    document.getElementById(input().getAttribute("aria-activedescendant")!);
  expect(highlighted()).toHaveTextContent("KDA 482M");
  fireEvent.keyDown(input(), { key: "ArrowDown" });
  expect(highlighted()).toHaveTextContent("KDB 100X");
  fireEvent.keyDown(input(), { key: "ArrowDown" });
  fireEvent.keyDown(input(), { key: "ArrowDown" });
  expect(highlighted()).toHaveTextContent("KDA 482M");
  fireEvent.keyDown(input(), { key: "ArrowUp" });
  expect(highlighted()).toHaveTextContent("KDC 200Y");
});

it("opens with the arrow key when closed, on the chosen option", () => {
  render(<Harness start="v3" />);
  fireEvent.keyDown(input(), { key: "ArrowDown" });
  expect(input()).toHaveAttribute("aria-expanded", "true");
  expect(
    document.getElementById(input().getAttribute("aria-activedescendant")!),
  ).toHaveTextContent("KDC 200Y");
});

it("takes the highlighted option with Enter and shows its label", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  fireEvent.focus(input());
  fireEvent.keyDown(input(), { key: "ArrowDown" });
  fireEvent.keyDown(input(), { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("v2");
  expect(input()).toHaveValue("KDB 100X, Rongai Express");
  expect(input()).toHaveAttribute("aria-expanded", "false");
});

it("takes the first match of what was typed with Enter", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "kdc" } });
  fireEvent.keyDown(input(), { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("v3");
});

it("takes what was typed with Tab, and lets Tab move on", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "metro" } });
  const tab = fireEvent.keyDown(input(), { key: "Tab" });
  expect(tab).toBe(true);
  expect(onChange).toHaveBeenCalledWith("v3");
  expect(input()).toHaveValue("KDC 200Y, Metro Trans");
});

it("keeps the choice when Tab leaves without typing", () => {
  const onChange = vi.fn();
  render(<Harness start="v1" onChange={onChange} />);
  fireEvent.focus(input());
  fireEvent.keyDown(input(), { key: "ArrowDown" });
  fireEvent.keyDown(input(), { key: "Tab" });
  expect(onChange).not.toHaveBeenCalled();
  expect(input()).toHaveValue("KDA 482M, Rongai Express");
  expect(input()).toHaveAttribute("aria-expanded", "false");
});

it("closes on Escape without choosing, forgetting what was typed", () => {
  const onChange = vi.fn();
  render(<Harness start="v1" onChange={onChange} />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "kdc" } });
  fireEvent.keyDown(input(), { key: "Escape" });
  expect(input()).toHaveAttribute("aria-expanded", "false");
  expect(onChange).not.toHaveBeenCalled();
  expect(input()).toHaveValue("KDA 482M, Rongai Express");
});

it("closes when it loses focus", () => {
  render(<Harness start="v1" />);
  fireEvent.focus(input());
  fireEvent.blur(input());
  expect(input()).toHaveAttribute("aria-expanded", "false");
});

it("takes an option that is clicked or tapped, without letting the input lose focus first", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  fireEvent.focus(input());
  const option = screen.getByRole("option", { name: /KDC/ });
  expect(fireEvent.mouseDown(option)).toBe(false);
  fireEvent.click(option);
  expect(onChange).toHaveBeenCalledWith("v3");
  expect(input()).toHaveValue("KDC 200Y, Metro Trans");
});

it("highlights the option the pointer is over", () => {
  render(<Harness />);
  fireEvent.focus(input());
  fireEvent.mouseMove(screen.getByRole("option", { name: /KDB/ }));
  expect(
    document.getElementById(input().getAttribute("aria-activedescendant")!),
  ).toHaveTextContent("KDB 100X");
});

it("jumps to the first and last match with Home and End while searching", () => {
  render(<Harness />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "rongai" } });
  fireEvent.keyDown(input(), { key: "End" });
  expect(
    document.getElementById(input().getAttribute("aria-activedescendant")!),
  ).toHaveTextContent("KDB 100X");
  fireEvent.keyDown(input(), { key: "Home" });
  expect(
    document.getElementById(input().getAttribute("aria-activedescendant")!),
  ).toHaveTextContent("KDA 482M");
});

it("shows each option's group beside it, as the design's item list does", () => {
  render(
    <Harness
      options={[
        { value: "i1", label: "Tyres", group: "Garage and repairs" },
        { value: "i2", label: "Brake pads", group: "Garage and repairs" },
        { value: "i3", label: "Parking", group: "Fees" },
      ]}
    />,
  );
  fireEvent.focus(input());
  const list = listboxOf(input());
  expect(within(list).getAllByText("Garage and repairs")).toHaveLength(2);
  expect(within(list).getByText("Fees")).toBeInTheDocument();
  fireEvent.change(input(), { target: { value: "fees park" } });
  const found = within(listboxOf(input())).getAllByRole("option");
  expect(found).toHaveLength(1);
  expect(found[0]).toHaveAccessibleName("Parking");
});

it("takes the id and the error wiring of the field it is in", () => {
  render(
    <Field id="vehicle" label="Vehicle" error="Choose the vehicle.">
      <SearchSelect options={OPTIONS} value="" onChange={() => {}} />
    </Field>,
  );
  const box = screen.getByLabelText("Vehicle");
  expect(box).toHaveAttribute("role", "combobox");
  expect(box).toHaveAttribute("aria-invalid", "true");
  expect(box).toHaveAttribute("aria-describedby", "vehicle-error");
});

it("can be set from the test helpers, and lists its options", () => {
  const onChange = vi.fn();
  render(<Harness onChange={onChange} />);
  expect(optionsOf(input())).toHaveLength(3);
  pick(input(), /KDB/);
  expect(onChange).toHaveBeenCalledWith("v2");
});

it("does not open while disabled", () => {
  render(
    <SearchSelect
      aria-label="Vehicle"
      options={OPTIONS}
      value=""
      disabled
      onChange={() => {}}
    />,
  );
  expect(input()).toBeDisabled();
});

it.each(RANK_VECTORS)("ranks as the shared rule does: $name", (vector) => {
  render(
    <SearchSelect
      aria-label="Vehicle"
      options={vector.options.map((option, index) => ({
        value: `o${index}`,
        ...(typeof option === "string" ? { label: option } : option),
      }))}
      value=""
      onChange={() => {}}
    />,
  );
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: vector.query } });
  expect(
    within(listboxOf(input())).queryAllByRole("option").map(nameOf),
  ).toEqual(vector.expected);
});

function AddHarness({ onAdd }: { onAdd?: (typed: string) => void }) {
  return (
    <SearchSelect
      aria-label="Vehicle"
      options={OPTIONS}
      value=""
      onChange={() => {}}
      onAdd={onAdd}
    />
  );
}

it("offers no way to add without onAdd, as for someone who may not create the record", () => {
  render(<AddHarness />);
  expect(optionsOf(input())).not.toContain("+ Add new");
  fireEvent.change(input(), { target: { value: "zzz" } });
  expect(within(listboxOf(input())).queryAllByRole("option")).toHaveLength(0);
});

it("pins + Add new as the last option, under the ranked matches", () => {
  render(<AddHarness onAdd={() => {}} />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "rongai" } });
  expect(within(listboxOf(input())).getAllByRole("option").map(nameOf)).toEqual(
    ["KDA 482M, Rongai Express", "KDB 100X, Rongai Express", "+ Add new"],
  );
});

it("reaches + Add new with the arrow keys and hands Enter what was typed", () => {
  const onAdd = vi.fn();
  render(<AddHarness onAdd={onAdd} />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "  KDE 300Z " } });
  const highlighted = () =>
    document.getElementById(input().getAttribute("aria-activedescendant")!);
  expect(highlighted()).toHaveTextContent("+ Add new");
  fireEvent.keyDown(input(), { key: "ArrowUp" });
  fireEvent.keyDown(input(), { key: "ArrowDown" });
  expect(highlighted()).toHaveTextContent("+ Add new");
  fireEvent.keyDown(input(), { key: "Enter" });
  expect(onAdd).toHaveBeenCalledWith("KDE 300Z");
  expect(input()).toHaveAttribute("aria-expanded", "false");
});

it("wraps from the first match up to + Add new, and adds on a click", () => {
  const onAdd = vi.fn();
  render(<AddHarness onAdd={onAdd} />);
  fireEvent.focus(input());
  fireEvent.keyDown(input(), { key: "ArrowUp" });
  expect(
    document.getElementById(input().getAttribute("aria-activedescendant")!),
  ).toHaveTextContent("+ Add new");
  fireEvent.click(
    within(listboxOf(input())).getByRole("option", { name: "+ Add new" }),
  );
  expect(onAdd).toHaveBeenCalledWith("");
});

it("never adds on Tab, which only moves on", () => {
  const onAdd = vi.fn();
  render(<AddHarness onAdd={onAdd} />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: "zzz" } });
  fireEvent.keyDown(input(), { key: "Tab" });
  expect(onAdd).not.toHaveBeenCalled();
  expect(input()).toHaveAttribute("aria-expanded", "false");
});

it("shows typed markup as plain text, never as elements", () => {
  const typed = '<img src=x onerror="window.__xss=1"><b>bold</b>';
  render(<AddHarness onAdd={() => {}} />);
  fireEvent.focus(input());
  fireEvent.change(input(), { target: { value: typed } });
  const listbox = listboxOf(input());
  expect(listbox.querySelector("img, b, script")).toBeNull();
  expect(listbox).toHaveTextContent(typed);
  expect((window as { __xss?: number }).__xss).toBeUndefined();
});
