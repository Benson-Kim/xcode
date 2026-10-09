import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { Pager, pageCount, pageItems, usePaging } from "../components/ui";
import { optionsOf, pick } from "./searchSelect";

it.each([
  [1, 1, [1]],
  [1, 5, [1, 2, 3, 4, 5]],
  [3, 7, [1, 2, 3, 4, 5, 6, 7]],
  [1, 25, [1, 2, 3, "gap", 25]],
  [6, 25, [1, "gap", 4, 5, 6, 7, 8, "gap", 25]],
  [25, 25, [1, "gap", 23, 24, 25]],
  [4, 25, [1, 2, 3, 4, 5, 6, "gap", 25]],
  [5, 25, [1, 2, 3, 4, 5, 6, 7, "gap", 25]],
  [22, 25, [1, "gap", 20, 21, 22, 23, 24, 25]],
])("lists page %i of %i as %j", (page, pages, expected) => {
  expect(pageItems(page, pages)).toEqual(expected);
});

it("counts at least one page", () => {
  expect(pageCount(0, 50)).toBe(1);
  expect(pageCount(50, 50)).toBe(1);
  expect(pageCount(51, 50)).toBe(2);
  expect(pageCount(1234, 50)).toBe(25);
});

function show(over: Partial<Parameters<typeof Pager>[0]> = {}) {
  const props = {
    page: 1,
    pageSize: 50,
    total: 1234,
    onPageChange: vi.fn(),
    onPageSizeChange: vi.fn(),
    ...over,
  };
  render(<Pager {...props} />);
  return props;
}

const labels = () =>
  within(screen.getByRole("navigation", { name: "Pages" }))
    .getAllByRole("button")
    .map((button) => button.getAttribute("aria-label"));

it("says which rows are shown of how many, with the organization's number format", () => {
  show({ page: 2, total: 1234 });
  expect(screen.getByText("Showing 51–100 of 1,234")).toBeInTheDocument();
});

it("ends the last page at the total", () => {
  show({ page: 25, total: 1234 });
  expect(screen.getByText("Showing 1,201–1,234 of 1,234")).toBeInTheDocument();
});

it("offers real buttons for the ends, the neighbours and the pages around the current one", () => {
  show({ page: 6, total: 1234 });
  expect(labels()).toEqual([
    "First page",
    "Previous page",
    "Page 1",
    "Page 4",
    "Page 5",
    "Page 6",
    "Page 7",
    "Page 8",
    "Page 25",
    "Next page",
    "Last page",
  ]);
  const nav = screen.getByRole("navigation", { name: "Pages" });
  for (const button of within(nav).getAllByRole("button"))
    expect(button.tagName).toBe("BUTTON");
  expect(nav.textContent).toContain("…");
  expect(screen.getByRole("button", { name: "Page 6" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(screen.getByRole("button", { name: "Page 5" })).not.toHaveAttribute(
    "aria-current",
  );
});

it("moves to the page of the button chosen", () => {
  const props = show({ page: 6 });
  fireEvent.click(screen.getByRole("button", { name: "Page 8" }));
  expect(props.onPageChange).toHaveBeenLastCalledWith(8);
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(props.onPageChange).toHaveBeenLastCalledWith(7);
  fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
  expect(props.onPageChange).toHaveBeenLastCalledWith(5);
  fireEvent.click(screen.getByRole("button", { name: "First page" }));
  expect(props.onPageChange).toHaveBeenLastCalledWith(1);
  fireEvent.click(screen.getByRole("button", { name: "Last page" }));
  expect(props.onPageChange).toHaveBeenLastCalledWith(25);
});

it("can be used from the keyboard: the buttons take focus and are named", () => {
  show({ page: 2 });
  const next = screen.getByRole("button", { name: "Next page" });
  next.focus();
  expect(next).toHaveFocus();
  expect(next).toHaveAttribute("type", "button");
});

it("disables going back on the first page and forward on the last", () => {
  const { unmount } = render(
    <Pager
      page={1}
      pageSize={50}
      total={120}
      onPageChange={() => {}}
      onPageSizeChange={() => {}}
    />,
  );
  expect(screen.getByRole("button", { name: "First page" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Next page" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Last page" })).toBeEnabled();
  unmount();
  render(
    <Pager
      page={3}
      pageSize={50}
      total={120}
      onPageChange={() => {}}
      onPageSizeChange={() => {}}
    />,
  );
  expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Last page" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled();
});

it("offers 25, 50 and 100 rows per page and reports the one chosen", () => {
  const props = show({ pageSize: 50 });
  const select = screen.getByLabelText("Rows per page");
  expect(select).toHaveAttribute("role", "combobox");
  expect(optionsOf(select)).toEqual(["25", "50", "100"]);
  expect(select).toHaveValue("50");
  pick(select, "100");
  expect(props.onPageSizeChange).toHaveBeenCalledWith(100);
});

it("searches the sizes by typing", () => {
  const props = show({ pageSize: 50 });
  const select = screen.getByLabelText("Rows per page");
  fireEvent.focus(select);
  fireEvent.change(select, { target: { value: "2" } });
  fireEvent.keyDown(select, { key: "Enter" });
  expect(props.onPageSizeChange).toHaveBeenCalledWith(25);
});

it("is one bar with the rows per page on the left, the count in the middle and the page buttons on the right", () => {
  show({ page: 2, total: 1234 });
  const count = screen.getByText("Showing 51–100 of 1,234");
  const bar = count.parentElement!;
  expect(bar.className).toContain("rounded-[14px]");
  expect(bar.className).toContain("bg-surface");
  const [left, middle, right] = [...bar.children];
  expect(
    within(left as HTMLElement).getByLabelText("Rows per page"),
  ).toBeInTheDocument();
  expect(middle).toBe(count);
  expect(
    within(right as HTMLElement).getByRole("button", { name: "Next page" }),
  ).toBeInTheDocument();
});

it("draws the ends and the neighbours as arrows, not words", () => {
  show({ page: 6 });
  const nav = screen.getByRole("navigation", { name: "Pages" });
  for (const name of [
    "First page",
    "Previous page",
    "Next page",
    "Last page",
  ]) {
    const button = within(nav).getByRole("button", { name });
    expect(button.textContent).toBe("");
    expect(button.querySelector("svg")).not.toBeNull();
  }
  expect(within(nav).queryByText(/first|previous|next|last/i)).toBeNull();
});

it("lists a page size that is not among the choices rather than hiding it", () => {
  show({ pageSize: 10, total: 100 });
  expect(screen.getByLabelText("Rows per page")).toHaveValue("10");
});

it("shows nothing while everything fits the smallest page", () => {
  const { container } = render(
    <Pager
      page={1}
      pageSize={50}
      total={25}
      onPageChange={() => {}}
      onPageSizeChange={() => {}}
    />,
  );
  expect(container).toBeEmptyDOMElement();
});

it("shows only the count and the size when everything fits one page above 25", () => {
  show({ total: 40, pageSize: 50 });
  expect(screen.getByText("Showing 1–40 of 40")).toBeInTheDocument();
  expect(screen.getByLabelText("Rows per page")).toBeInTheDocument();
  expect(
    screen.queryByRole("navigation", { name: "Pages" }),
  ).not.toBeInTheDocument();
});

function Harness({ filter }: { filter: string }) {
  const paging = usePaging(filter, 50);
  return (
    <div>
      <output aria-label="state">{`${paging.page}/${paging.pageSize}`}</output>
      <button onClick={() => paging.setPage(3)}>go to 3</button>
      <button onClick={() => paging.setPageSize(25)}>size 25</button>
      <button onClick={() => paging.stepBack(60)}>step back to 60 rows</button>
    </div>
  );
}

const state = () => screen.getByLabelText("state").textContent;

it("goes back to page 1 when the page size changes, keeping the size", () => {
  render(<Harness filter="a" />);
  fireEvent.click(screen.getByText("go to 3"));
  expect(state()).toBe("3/50");
  fireEvent.click(screen.getByText("size 25"));
  expect(state()).toBe("1/25");
});

it("goes back to page 1 when the filters change, and keeps the size", () => {
  function Switch() {
    const [filter, setFilter] = useState("a");
    return (
      <>
        <button onClick={() => setFilter("b")}>filter b</button>
        <Harness filter={filter} />
      </>
    );
  }
  render(<Switch />);
  fireEvent.click(screen.getByText("size 25"));
  fireEvent.click(screen.getByText("go to 3"));
  expect(state()).toBe("3/25");
  fireEvent.click(screen.getByText("filter b"));
  expect(state()).toBe("1/25");
});

it("steps back to the last page that exists, and leaves a page that still exists", () => {
  render(<Harness filter="a" />);
  fireEvent.click(screen.getByText("go to 3"));
  fireEvent.click(screen.getByText("step back to 60 rows"));
  expect(state()).toBe("2/50");
  fireEvent.click(screen.getByText("step back to 60 rows"));
  expect(state()).toBe("2/50");
});
