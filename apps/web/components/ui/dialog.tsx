"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

import { IconButton } from "./button";
import { CloseIcon } from "./icons";

// A modal panel with a sticky title bar (.access-dialog). Escape and the close button both call onClose, once.
// The native close event that follows a close the parent asked for is ignored.
export function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
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
      className="m-auto max-h-[calc(100%-64px)] w-[min(520px,calc(100%-32px))] rounded-2xl border border-card-line p-0 text-navy backdrop:bg-navy/40"
    >
      <div className="sticky top-0 flex items-center justify-between border-b border-card-line bg-surface px-5 py-4">
        <h2 id={titleId} className="m-0 text-xl font-bold">
          {title}
        </h2>
        <IconButton aria-label="Close" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </div>
      <div className="px-5 pt-4 pb-6">{children}</div>
    </dialog>
  );
}
