"use client";

import {
  useCallback,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import type { ReportExportFormat } from "@xcode/shared/reports";

import { Button, ChevronIcon, useDismiss } from "../ui";

export const EXPORT_FORMATS: {
  format: ReportExportFormat;
  label: string;
}[] = [
  { format: "xlsx", label: "Excel" },
  { format: "pdf", label: "PDF" },
];

// The Export button: it opens a short menu to choose the file, Excel or PDF.
export function ExportMenu({
  disabled,
  onExport,
}: {
  disabled: boolean;
  onExport: (format: ReportExportFormat) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) trigger.current?.focus();
  }, []);
  useDismiss(open, wrapper, close);

  function move(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const items = [
      ...event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'),
    ];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    items[(at + step + items.length) % items.length]?.focus();
  }

  return (
    <div ref={wrapper} className="relative">
      <Button
        ref={trigger}
        tone="outline"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        Export
        <ChevronIcon />
      </Button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Export as"
          onKeyDown={move}
          className="absolute top-full right-0 z-40 mt-2 min-w-40 rounded-xl border border-card-line bg-surface p-1.5 shadow-menu"
        >
          {EXPORT_FORMATS.map((option, index) => (
            <button
              key={option.format}
              type="button"
              role="menuitem"
              autoFocus={index === 0}
              onClick={() => {
                close(true);
                onExport(option.format);
              }}
              className="block min-h-11 w-full rounded-lg px-3 text-left text-[15px] hover:bg-hover"
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
