"use client";

import { createContext, useEffect, useId, useRef, type ReactNode } from "react";

import { cn } from "./cn";
import { CloseIcon } from "./icons";

export const InDialogContext = createContext(false);

const WIDTHS = {
  sm: "w-[min(520px,calc(100vw-32px))]",
  md: "w-[min(700px,calc(100vw-32px))]",
  lg: "w-[min(960px,calc(100vw-32px))]",
} as const;

// A modal panel: title bar, scrolling body and an optional pinned footer. Escape and the close button both call
// onClose, once. The native close event that follows a close the parent asked for is ignored.
export function Dialog({
  open,
  title,
  subtitle,
  size = "sm",
  onClose,
  footer,
  children,
}: {
  open: boolean;
  title: string;
  // md fits a table, such as a day's revenue for every vehicle; lg is for the big forms.
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
      className={cn(
        "m-auto max-h-[88%] flex-col overflow-hidden rounded-3xl border-0 bg-surface p-0 text-ink-2 shadow-[0_24px_60px_rgba(4,32,47,.24),0_2px_8px_rgba(4,32,47,.24)] backdrop:bg-scrim open:flex motion-safe:transition-[opacity,translate] motion-safe:duration-150 motion-safe:open:starting:translate-y-2.5 motion-safe:open:starting:opacity-0",
        "max-[600px]:mx-0 max-[600px]:mt-auto max-[600px]:mb-0 max-[600px]:max-h-[92%] max-[600px]:w-full max-[600px]:max-w-full max-[600px]:rounded-t-[20px] max-[600px]:rounded-b-none",
        WIDTHS[size],
      )}
    >
      <div className="flex flex-none items-start justify-between gap-4 px-[22px] pt-[18px] pb-3.5">
        <div className="min-w-0">
          <h2
            id={titleId}
            className="m-0 text-[19px] leading-snug font-extrabold text-ink"
          >
            {title}
          </h2>
          {subtitle && (
            <p className="m-0 mt-1 text-[13.5px] font-semibold text-slate">
              {subtitle}
            </p>
          )}
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="grid size-[34px] flex-none place-items-center rounded-full bg-paper text-ink hover:bg-paper-2"
        >
          <CloseIcon />
        </button>
      </div>
      <InDialogContext.Provider value>
        <div className="flex min-h-0 flex-col gap-3.5 overflow-auto px-[22px] pt-1 pb-5">
          {children}
        </div>
      </InDialogContext.Provider>
      {footer && (
        <div className="flex flex-none flex-wrap items-center justify-end gap-2.5 border-t border-line bg-paper px-[22px] pt-3.5 pb-[calc(14px+env(safe-area-inset-bottom,0px))] max-[600px]:[&_button]:flex-1 [&_button]:min-w-27">
          {footer}
        </div>
      )}
    </dialog>
  );
}
