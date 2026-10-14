"use client";

import {
  useCallback,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

import { ChevronIcon, popLayer, useAnchoredPosition, useDismiss } from "../ui";

export type RowMenuItem = {
  label: string;
  tone?: "bad";
  onSelect: () => void;
};

// The less used actions of a row under one "More" button (.act.more) that opens a small list (.pop.row), lined up
// with the button's right edge.
export function RowMenu({
  label,
  items,
  disabled,
}: {
  label: string;
  items: RowMenuItem[];
  disabled?: boolean;
}) {
  const [layer, setLayer] = useState<HTMLElement | null>(null);
  const open = layer !== null;
  const wrapper = useRef<HTMLSpanElement>(null);
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
    const found = [
      ...event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'),
    ];
    const at = found.indexOf(document.activeElement as HTMLElement);
    const step = event.key === "ArrowDown" ? 1 : -1;
    found[(at + step + found.length) % found.length]?.focus();
  }

  return (
    <span ref={wrapper}>
      <button
        ref={trigger}
        type="button"
        className="act plain more disabled:cursor-default disabled:opacity-45"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`More ${label}`}
        disabled={disabled}
        onClick={(event) =>
          setLayer(open ? null : popLayer(event.currentTarget))
        }
      >
        More
        <ChevronIcon />
      </button>
      {layer &&
        createPortal(
          <div
            ref={menu}
            id={menuId}
            role="menu"
            aria-label={`More actions, ${label}`}
            onKeyDown={move}
            className="pop row"
          >
            <div className="plist">
              {items.map((item, index) => (
                <button
                  key={item.label}
                  type="button"
                  role="menuitem"
                  className={item.tone}
                  autoFocus={index === 0}
                  onClick={() => {
                    close(false);
                    item.onSelect();
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>,
          layer,
        )}
    </span>
  );
}
