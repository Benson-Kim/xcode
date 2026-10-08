import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import PageError from "../app/error";
import GlobalError from "../app/global-error";

it("global error shows a reload button", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  render(<GlobalError />);
  expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Reload the app" }),
  ).toBeInTheDocument();
});

it("page error offers to try again", () => {
  const reset = vi.fn();
  render(<PageError error={new Error("boom")} reset={reset} />);
  expect(screen.getByText("This page ran into a problem")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(reset).toHaveBeenCalledOnce();
});
