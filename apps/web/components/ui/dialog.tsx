"use client";

import { createContext, useEffect, useId, useRef, type ReactNode } from "react";

import { cn } from "./cn";
import { CloseIcon } from "./icons";

export const InDialogContext = createContext(false);

// The design's one pop up shell (<dialog class="sm|md|lg">): title bar (.mh), scrolling body (.mb) and the actions
// pinned under it (.mf). A centred card on a desk screen, a bottom sheet on a phone. Escape and the close button both
// call onClose, once. The native close event that follows a close the parent asked for is ignored.
export function Dialog({
  open,
  title,
  subtitle,
  size,
  onClose,
  footer,
  children,
}: {
  open: boolean;
  title: string;
  // No size is the design's standard pop up (520px). sm is its short forms (430px), md fits a table, such as a
  // day's revenue for every vehicle, and lg is for the big forms.
  size?: "sm" | "md" | "lg";
  // A line under the title, such as who recorded what is being changed.
  subtitle?: string;
  onClose: () => void;
  // Actions pinned under the body.
  footer?: ReactNode;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const openRef = useRef(open);
  const titleId = useId();
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
      onClose={() => {
        if (openRef.current) onClose();
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
          onClick={onClose}
        >
          <CloseIcon />
        </button>
      </div>
      <InDialogContext.Provider value>
        <div className="mb">{children}</div>
      </InDialogContext.Provider>
      {footer && <div className="mf">{footer}</div>}
    </dialog>
  );
}
