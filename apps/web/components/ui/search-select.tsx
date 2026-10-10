"use client";

import {
  useId,
  useMemo,
  useState,
  type ComponentProps,
  type KeyboardEvent,
} from "react";

import { cn } from "./cn";
import { useFieldProps } from "./form";
import { ChevronIcon } from "./icons";

export type SearchOption = {
  value: string;
  label: string;
  // Options with the same group sit together under its name.
  group?: string;
};

const DENSITY = {
  standard:
    "py-[9px] text-[14.5px] in-[dialog]:py-[11px] in-[dialog]:text-[15px] max-[600px]:in-[dialog]:text-base",
  compact: "py-[7px] text-[14px] in-[dialog]:py-[9px]",
} as const;

const words = (text: string) => text.toLowerCase().split(/\s+/).filter(Boolean);

// A dropdown that can be searched: a combobox over a listbox. Typing narrows the options, the arrow keys move
// through them, Enter or Tab takes the highlighted one, Escape closes. A click or a tap takes an option too.
export function SearchSelect({
  options,
  value,
  onChange,
  placeholder = "Choose",
  emptyText = "Nothing matches",
  density = "standard",
  inline = false,
  disabled = false,
  className,
  ...props
}: {
  options: readonly SearchOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyText?: string;
  density?: keyof typeof DENSITY;
  // Sized to a toolbar rather than the width of its column.
  inline?: boolean;
  disabled?: boolean;
  className?: string;
} & Pick<
  ComponentProps<"input">,
  "id" | "aria-label" | "aria-describedby" | "aria-invalid" | "autoFocus"
>) {
  const field = useFieldProps(props);
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  const chosen = options.find((option) => option.value === value);
  const shown = useMemo(() => {
    const wanted = words(query ?? "");
    if (!wanted.length) return options;
    return options.filter((option) => {
      const text = `${option.group ?? ""} ${option.label}`.toLowerCase();
      return wanted.every((word) => text.includes(word));
    });
  }, [options, query]);

  const optionId = (index: number) => `${listId}-${index}`;
  const activeId = open && shown[active] ? optionId(active) : undefined;

  function show() {
    setQuery(null);
    setActive(
      Math.max(
        0,
        options.findIndex((option) => option.value === value),
      ),
    );
    setOpen(true);
  }

  function type(text: string) {
    setQuery(text);
    setActive(0);
    setOpen(true);
  }

  function close() {
    setOpen(false);
    setQuery(null);
  }

  function pick(option: SearchOption | undefined) {
    if (option) onChange(option.value);
    close();
  }

  function move(step: number) {
    if (!open) return show();
    if (shown.length)
      setActive((at) => (at + step + shown.length) % shown.length);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        return move(1);
      case "ArrowUp":
        event.preventDefault();
        return move(-1);
      case "Home":
      case "End":
        if (!open || query === null) return;
        event.preventDefault();
        return setActive(event.key === "Home" ? 0 : shown.length - 1);
      case "Enter":
        if (!open) return;
        event.preventDefault();
        return pick(shown[active]);
      case "Tab":
        if (open && query !== null) pick(shown[active]);
        else close();
        return;
      case "Escape":
        if (!open) return;
        event.preventDefault();
        event.stopPropagation();
        return close();
    }
  }

  return (
    <div className={cn("relative", inline ? "w-auto min-w-0" : "w-full")}>
      <input
        {...field}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        placeholder={placeholder}
        value={open && query !== null ? query : (chosen?.label ?? "")}
        onFocus={(event) => {
          event.target.select();
          show();
        }}
        onClick={() => !open && show()}
        onChange={(event) => type(event.target.value)}
        onBlur={close}
        onKeyDown={onKeyDown}
        className={cn(
          "rounded-[10px] border border-line bg-surface px-3 pr-9 text-ink placeholder:text-slate/70 focus:border-teal focus:outline-3 focus:outline-offset-1 focus:outline-teal/30 aria-invalid:border-clay aria-invalid:bg-clay-wash disabled:bg-paper disabled:text-slate",
          DENSITY[density],
          inline ? "w-48 max-w-full min-w-0" : "w-full",
          className,
        )}
      />
      <ChevronIcon
        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-slate"
        aria-hidden="true"
      />
      <Listbox
        id={listId}
        open={open}
        shown={shown}
        value={value}
        active={active}
        emptyText={emptyText}
        onPick={pick}
        onHover={setActive}
      />
    </div>
  );
}

function Listbox({
  id,
  open,
  shown,
  value,
  active,
  emptyText,
  onPick,
  onHover,
}: {
  id: string;
  open: boolean;
  shown: readonly SearchOption[];
  value: string;
  active: number;
  emptyText: string;
  onPick: (option: SearchOption) => void;
  onHover: (index: number) => void;
}) {
  return (
    <ul
      id={id}
      role="listbox"
      hidden={!open}
      className="absolute top-full left-0 z-50 mt-1.5 max-h-[212px] w-full min-w-44 overflow-y-auto rounded-xl border border-line bg-surface shadow-[0_10px_24px_rgba(4,32,47,.24)] in-[dialog]:static"
    >
      {shown.length === 0 && (
        <li role="presentation" className="p-3 text-[14.5px] text-slate">
          {emptyText}
        </li>
      )}
      {shown.map((option, index) => (
        <Option
          key={option.value}
          id={`${id}-${index}`}
          option={option}
          heading={
            option.group && option.group !== shown[index - 1]?.group
              ? option.group
              : undefined
          }
          selected={option.value === value}
          highlighted={index === active}
          onPick={() => onPick(option)}
          onHover={() => onHover(index)}
        />
      ))}
    </ul>
  );
}

function Option({
  id,
  option,
  heading,
  selected,
  highlighted,
  onPick,
  onHover,
}: {
  id: string;
  option: SearchOption;
  heading?: string;
  selected: boolean;
  highlighted: boolean;
  onPick: () => void;
  onHover: () => void;
}) {
  return (
    <>
      {heading && (
        <li
          role="presentation"
          className="px-3 pt-2 pb-1 text-[12px] font-bold tracking-[.07em] text-slate uppercase"
        >
          {heading}
        </li>
      )}
      <li
        id={id}
        role="option"
        aria-selected={selected}
        // The input keeps focus: a press on an option must not blur it before the click lands.
        onMouseDown={(event) => event.preventDefault()}
        onClick={onPick}
        onMouseMove={onHover}
        className={cn(
          "cursor-pointer border-b border-divider px-3 py-[9px] text-[14.5px] font-semibold text-ink last:border-b-0 aria-selected:font-bold",
          highlighted && "bg-teal-wash",
        )}
      >
        {option.label}
      </li>
    </>
  );
}
