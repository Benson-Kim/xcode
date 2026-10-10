import type { KeyboardEvent, ReactNode } from "react";

import { cn } from "./cn";

// On the sheet the panel is not a box of its own: its bars and cards keep the page's side margin and a table in it
// runs edge to edge, as a table straight on the sheet does (.pagebody > .tbl).
const PANEL_ON_SHEET =
  "[.pagebody>&]:mx-0 [.pagebody>&]:flex [.pagebody>&]:flex-col [.pagebody>&]:gap-3.5 [.pagebody>&>*]:mx-(--gut) [.pagebody>&>.tbl]:mx-0 [.pagebody>&>.tbl]:rounded-none [.pagebody>&>.tbl]:border-x-0 [.pagebody>&>.tbl_th:first-child]:pl-(--gut) [.pagebody>&>.tbl_td:first-child]:pl-(--gut) [.pagebody>&>.tbl_th:last-child]:pr-(--gut) [.pagebody>&>.tbl_td:last-child]:pr-(--gut)";

// Button cards at the top of a screen that show one part of it at a time (.tabs > .tab, a name over a count).
// Arrow keys, Home and End move between them; the chosen part is the tab panel below. They keep the tab roles, so the
// chosen one is aria-selected and takes the design's pressed look from that.
// With `aside` the buttons stack beside it, and the up and down arrows move between them too.
export function Tabs<T extends string>({
  id,
  label,
  options,
  value,
  onChange,
  className,
  aside,
  children,
}: {
  id: string;
  label: string;
  options: { value: T; label: string; note?: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const stacked = aside !== undefined;
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = options.length - 1;
    const forward =
      event.key === "ArrowRight" || (stacked && event.key === "ArrowDown");
    const back =
      event.key === "ArrowLeft" || (stacked && event.key === "ArrowUp");
    const next = forward
      ? index === last
        ? 0
        : index + 1
      : back
        ? index === 0
          ? last
          : index - 1
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? last
            : null;
    if (next === null) return;
    event.preventDefault();
    onChange(options[next].value);
    document.getElementById(`${id}-tab-${options[next].value}`)?.focus();
  }
  const list = (
    <div
      role="tablist"
      aria-label={label}
      aria-orientation={stacked ? "vertical" : undefined}
      className={cn(
        stacked ? "flex min-w-40 flex-col gap-3 max-[900px]:flex-row" : "tabs",
        !stacked && className,
      )}
    >
      {options.map((option, index) => (
        <button
          key={option.value}
          id={`${id}-tab-${option.value}`}
          type="button"
          role="tab"
          aria-selected={option.value === value}
          aria-controls={`${id}-panel`}
          tabIndex={option.value === value ? 0 : -1}
          onClick={() => onChange(option.value)}
          onKeyDown={(event) => move(event, index)}
          className={cn(
            "tab aria-selected:border-teal aria-selected:bg-teal-wash",
            stacked && "flex-1",
          )}
        >
          <span>{option.label}</span>
          {option.note !== undefined && <small>{option.note}</small>}
        </button>
      ))}
    </div>
  );
  return (
    <>
      {stacked ? (
        <div
          className={cn(
            "flex items-stretch gap-3.5 max-[900px]:flex-col",
            className,
          )}
        >
          {list}
          <div className="min-w-0 flex-1">{aside}</div>
        </div>
      ) : (
        list
      )}
      <div
        role="tabpanel"
        id={`${id}-panel`}
        aria-labelledby={`${id}-tab-${value}`}
        className={PANEL_ON_SHEET}
      >
        {children}
      </div>
    </>
  );
}
