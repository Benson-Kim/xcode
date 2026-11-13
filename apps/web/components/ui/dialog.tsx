"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cn } from "./cn";
import { CloseIcon } from "./icons";

export const InDialogContext = createContext(false);
const HoldContext = createContext<((on: boolean) => void) | null>(null);

// Keeps the dialog this form sits in open while busy, such as while its save runs.
export function useDialogBusy(busy: boolean) {
  const hold = useContext(HoldContext);
  useEffect(() => {
    if (!busy || !hold) return;
    hold(true);
    return () => hold(false);
  }, [busy, hold]);
}

// The design's one pop up shell (<dialog class="sm|md|lg">): title bar (.mh), scrolling body (.mb) and the actions
// pinned under it (.mf). A centred card on a desk screen, a bottom sheet on a phone. Escape, the close button and a
// click outside call onClose, once. The click counts only when the press starts and ends outside, so a selection
// dragged out of the dialog keeps it open. While the dialog is busy none of them closes it, so a save that lands
// after a close never acts on a form the user left. The native close event that follows a close the parent asked
// for is ignored.
export function Dialog({
  open,
  title,
  subtitle,
  size,
  busy = false,
  onClose,
  footer,
  children,
}: {
  open: boolean;
  title: string;
  // No size is the design's standard pop up (520px). sm is its short forms (430px), md fits a table, such as a
  // day's revenue for every vehicle, lg is for the big forms, tg the targets pop up with its history (820px) and
  // xl the person pop up with its side menu (1100px).
  size?: "sm" | "md" | "lg" | "tg" | "xl";
  // A line under the title, such as who recorded what is being changed.
  subtitle?: string;
  // Saving: Escape, the close button and a click outside leave it open.
  busy?: boolean;
  onClose: () => void;
  // Actions pinned under the body.
  footer?: ReactNode;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const openRef = useRef(open);
  const titleId = useId();
  const [holds, setHolds] = useState(0);
  const hold = useCallback(
    (on: boolean) => setHolds((count) => count + (on ? 1 : -1)),
    [],
  );
  // The box has no padding and its parts fill it, so a press on the dialog itself is a press on its backdrop.
  const pressedOutside = useRef(false);
  const locked = busy || holds > 0;
  useEffect(() => {
    openRef.current = open;
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      // React hands a nested dialog's close to this handler too; only this dialog's own close counts.
      onCancel={(event) => {
        if (event.target === event.currentTarget && locked)
          event.preventDefault();
      }}
      onClose={(event) => {
        if (event.target === event.currentTarget && openRef.current) onClose();
      }}
      onMouseDown={(event) => {
        pressedOutside.current = event.target === event.currentTarget;
      }}
      onClick={(event) => {
        const outside =
          pressedOutside.current && event.target === event.currentTarget;
        pressedOutside.current = false;
        if (outside && !locked) onClose();
      }}
      // The reset takes away the browser's own centring; on a phone the sheet sits on the bottom edge.
      className={cn(
        size,
        "m-auto max-[600px]:mx-0 max-[600px]:mt-auto max-[600px]:mb-0",
      )}
    >
      <div className="mh">
        <div>
          <h2 id={titleId}>{title}</h2>
          {subtitle && <div className="msub">{subtitle}</div>}
        </div>
        <button
          type="button"
          className="mx"
          aria-label="Close"
          disabled={locked}
          onClick={onClose}
        >
          <CloseIcon />
        </button>
      </div>
      <InDialogContext.Provider value>
        <HoldContext.Provider value={hold}>
          <div className="mb">{children}</div>
        </HoldContext.Provider>
      </InDialogContext.Provider>
      {footer && <div className="mf">{footer}</div>}
    </dialog>
  );
}
