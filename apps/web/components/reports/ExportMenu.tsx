"use client";

import {
  useCallback,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import type { ReportExportFormat } from "@xcode/shared/reports";

import { Button, DownloadIcon, useDismiss } from "../ui";

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
        <DownloadIcon />
        Export
      </Button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Export as"
          onKeyDown={move}
          className="absolute top-full right-0 z-40 mt-2 flex min-w-[190px] flex-col gap-0.5 rounded-2xl border border-line bg-surface p-2 shadow-[0_18px_44px_rgba(4,32,47,.24)]"
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
              className="block w-full rounded-[9px] px-3 py-[9px] text-left text-[14.5px] font-semibold whitespace-nowrap text-ink hover:bg-paper"
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
