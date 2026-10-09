import { act, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { DataTable, Td, Tr } from "../components/ui";
import { streamError, useStreamedList } from "../lib/data";
import { renderInApp } from "./renderInApp";

// A list that reads every page of an API list, as the pages that need every row do.
function Companies() {
  const list = useStreamedList<{ id: string; name: string }>("setup/companies");
  return (
    <>
      <p>{streamError(list)}</p>
      <DataTable
        columns={[{ label: "Company" }]}
        loading={list.loading}
        pendingRows={list.pendingRows}
        isEmpty={!list.items.length}
        emptyMessage="None"
      >
        {list.items.map((item) => (
          <Tr key={item.id}>
            <Td>
              <button>{item.name}</button>
            </Td>
          </Tr>
        ))}
      </DataTable>
    </>
  );
}

// 60 companies over three pages of 25; pages 2 and 3 wait until the test releases them.
const company = (index: number) => ({
  id: `c-${index}`,
  name: `Company ${String(index).padStart(2, "0")}`,
  vehicleCount: 1,
});
let releaseNext: () => Promise<void>;

beforeEach(() => {
  const gates: (() => void)[] = [];
  releaseNext = () => act(async () => gates.shift()?.());
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      const page = Number(
        new URL(input, "http://app").searchParams.get("page"),
      );
      if (page > 1) await new Promise<void>((resolve) => gates.push(resolve));
      const items = Array.from({ length: page === 3 ? 10 : 25 }, (_, index) =>
        company((page - 1) * 25 + index + 1),
      );
      return new Response(
        JSON.stringify({ items, pageNumber: page, pageSize: 25, total: 60 }),
        { status: 200 },
      );
    }),
  );
});

// Counted straight from the DOM: role queries over 60 rows are slow in jsdom.
const table = () => screen.getByRole("table");
const rows = () => table().querySelectorAll("tbody tr:has(button)");
const placeholders = () =>
  table().querySelectorAll("tbody tr:not(:has(button))");

it("shows rows as each page arrives, with fewer placeholders every time", async () => {
  renderInApp(<Companies />);

  expect(await screen.findByText("Company 25")).toBeInTheDocument();
  expect(rows()).toHaveLength(25);
  expect(table()).toHaveAttribute("aria-busy", "true");
  expect(placeholders()).toHaveLength(2);

  await releaseNext();
  expect(await screen.findByText("Company 50")).toBeInTheDocument();
  expect(rows()).toHaveLength(50);
  expect(placeholders()).toHaveLength(1);

  await releaseNext();
  expect(await screen.findByText("Company 60")).toBeInTheDocument();
  expect(rows()).toHaveLength(60);
  expect(placeholders()).toHaveLength(0);
  expect(table()).not.toHaveAttribute("aria-busy");
});

it("says how much of the list is shown when a later page fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      const page = Number(
        new URL(input, "http://app").searchParams.get("page"),
      );
      if (page > 1)
        return new Response(JSON.stringify({ title: "Refused" }), {
          status: 400,
        });
      const items = Array.from({ length: 25 }, (_, index) =>
        company(index + 1),
      );
      return new Response(
        JSON.stringify({ items, pageNumber: 1, pageSize: 25, total: 60 }),
        { status: 200 },
      );
    }),
  );
  renderInApp(<Companies />);

  expect(
    await screen.findByText("Refused Showing 25 of 60."),
  ).toBeInTheDocument();
  expect(rows()).toHaveLength(25);
  expect(placeholders()).toHaveLength(0);
});
