import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { Dialog } from "../components/ui";

it("calls onClose once for Escape", () => {
  const onClose = vi.fn();
  render(
    <Dialog open title="Edit" onClose={onClose}>
      body
    </Dialog>,
  );
  const dialog = screen.getByRole("dialog");
  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  fireEvent(dialog, new Event("close"));
  expect(onClose).toHaveBeenCalledTimes(1);
});

it("does not call onClose again when the parent closes it from its own onClose", () => {
  const onClose = vi.fn();
  function Parent() {
    const [open, setOpen] = useState(true);
    return (
      <Dialog
        open={open}
        title="Edit"
        onClose={() => {
          onClose();
          setOpen(false);
        }}
      >
        body
      </Dialog>
    );
  }
  render(<Parent />);
  const dialog = screen.getByRole("dialog", { hidden: true });
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  fireEvent(dialog, new Event("close"));
  expect(onClose).toHaveBeenCalledTimes(1);
});

it("stays silent when the parent closes it without asking", () => {
  const onClose = vi.fn();
  const { rerender } = render(
    <Dialog open title="Edit" onClose={onClose}>
      body
    </Dialog>,
  );
  const dialog = screen.getByRole("dialog");
  rerender(
    <Dialog open={false} title="Edit" onClose={onClose}>
      body
    </Dialog>,
  );
  fireEvent(dialog, new Event("close"));
  expect(onClose).not.toHaveBeenCalled();
});
