"use client";

import {
  useCallback,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

import type { ReportExportFormat } from "@xcode/shared/reports";

import {
  Button,
  DownloadIcon,
  popLayer,
  useAnchoredPosition,
  useDismiss,
} from "../ui";

export const EXPORT_FORMATS: {
  format: ReportExportFormat;
  label: string;
}[] = [
  { format: "xlsx", label: "Excel" },
  { format: "pdf", label: "PDF" },
];

// The Export button (.btn with the download icon): it opens a pop over (.pop .plist) to choose the file, Excel or PDF,
// lined up with the button's right edge as in the design.
export function ExportMenu({
  disabled,
  onExport,
}: {
  disabled: boolean;
  onExport: (format: ReportExportFormat) => void;
}) {
  const [layer, setLayer] = useState<HTMLElement | null>(null);
  const open = layer !== null;
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const close = useCallback((returnFocus: boolean) => {
    setLayer(null);
    if (returnFocus) trigger.current?.focus();
  }, []);
  useDismiss(open, wrapper, close, menu);
  useAnchoredPosition(open, trigger, menu, { align: "end" });

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
    <div ref={wrapper}>
      <Button
        ref={trigger}
        tone="outline"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={disabled}
        onClick={(event) =>
          setLayer(open ? null : popLayer(event.currentTarget))
        }
      >
        <DownloadIcon />
        Export
      </Button>
      {layer &&
        createPortal(
          <div
            ref={menu}
            id={menuId}
            role="menu"
            aria-label="Export as"
            onKeyDown={move}
            className="pop"
          >
            <div className="plist">
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
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>,
          layer,
        )}
    </div>
  );
}
