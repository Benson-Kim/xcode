import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "../components/ui";

function Buttons() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast("A")}>show A</button>
      <button onClick={() => toast("B")}>show B</button>
    </>
  );
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it("keeps each toast's own four seconds when a newer one arrives", () => {
  render(
    <ToastProvider>
      <Buttons />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByText("show A"));
  act(() => vi.advanceTimersByTime(3000));
  fireEvent.click(screen.getByText("show B"));
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.queryByText("A")).toBeNull();
  expect(screen.getByText("B")).toBeInTheDocument();
  act(() => vi.advanceTimersByTime(3000));
  expect(screen.queryByText("B")).toBeNull();
});

it("is a silent no-op outside a provider", () => {
  render(<Buttons />);
  fireEvent.click(screen.getByText("show A"));
  expect(screen.queryByRole("status")).toBeNull();
});
