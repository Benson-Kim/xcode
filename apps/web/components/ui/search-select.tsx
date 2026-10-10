"use client";

import {
  useId,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type KeyboardEvent,
  type RefObject,
} from "react";

import { cn } from "./cn";
import { controlClass, useFieldProps } from "./form";
import { ChevronIcon } from "./icons";
import { useAnchoredPosition } from "./popover";

export type SearchOption = {
  value: string;
  label: string;
  // Options with the same group sit together under its name.
  group?: string;
};

// The design's control (.inp) sizes itself from where it sits, so both densities draw the same.
const DENSITY = {
  standard: "",
  compact: "",
} as const;

const words = (text: string) => text.toLowerCase().split(/\s+/).filter(Boolean);

// A dropdown that can be searched, as the design's item search (comboHtml): a combobox (.inp) over a listbox
// (.combolist) that opens in the flow of the form, each option (.copt) with its group in small type beside it.
// In a toolbar (`inline`) the list floats under the input instead. Typing narrows the options, the arrow keys move
// through them (the highlighted one is aria-selected), Enter or Tab takes it, Escape closes. A click or a tap takes
// an option too.
// The options whose group and label hold every word typed, in any order.
function useMatching(options: readonly SearchOption[], query: string | null) {
  return useMemo(() => {
    const wanted = words(query ?? "");
    if (!wanted.length) return options;
    return options.filter((option) => {
      const text = `${option.group ?? ""} ${option.label}`.toLowerCase();
      return wanted.every((word) => text.includes(word));
    });
  }, [options, query]);
}

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
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  const chosen = options.find((option) => option.value === value);
  const shown = useMatching(options, query);

  const optionId = (index: number) => `${listId}-${index}`;
  const activeId = open && shown[active] ? optionId(active) : undefined;
  useAnchoredPosition(open && inline, box, list, { gap: 0, matchWidth: true });

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
    <div
      ref={box}
      className={cn("combo relative", inline ? "w-auto min-w-0" : "w-full")}
    >
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
        className={controlClass(
          field["aria-invalid"],
          "pr-9",
          DENSITY[density],
          inline && "w-48 max-w-full",
          className,
        )}
      />
      <ChevronIcon
        size={16}
        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-slate"
        aria-hidden="true"
      />
      <Listbox
        listRef={list}
        floating={inline}
        id={listId}
        open={open}
        shown={shown}
        active={active}
        emptyText={emptyText}
        onPick={pick}
        onHover={setActive}
      />
    </div>
  );
}

function Listbox({
  listRef,
  floating,
  id,
  open,
  shown,
  active,
  emptyText,
  onPick,
  onHover,
}: {
  listRef: RefObject<HTMLDivElement | null>;
  floating: boolean;
  id: string;
  open: boolean;
  shown: readonly SearchOption[];
  active: number;
  emptyText: string;
  onPick: (option: SearchOption) => void;
  onHover: (index: number) => void;
}) {
  return (
    <div
      ref={listRef}
      id={id}
      role="listbox"
      hidden={!open}
      className={cn("combolist", floating && "z-50 min-w-44")}
    >
      {shown.length === 0 && (
        <div role="presentation" className="cnone">
          {emptyText}
        </div>
      )}
      {shown.map((option, index) => (
        <Option
          key={option.value}
          id={`${id}-${index}`}
          option={option}
          highlighted={index === active}
          onPick={() => onPick(option)}
          onHover={() => onHover(index)}
        />
      ))}
    </div>
  );
}

function Option({
  id,
  option,
  highlighted,
  onPick,
  onHover,
}: {
  id: string;
  option: SearchOption;
  highlighted: boolean;
  onPick: () => void;
  onHover: () => void;
}) {
  return (
    <div
      id={id}
      role="option"
      aria-selected={highlighted}
      className="copt cursor-pointer"
      // The input keeps focus: a press on an option must not blur it before the click lands.
      onMouseDown={(event) => event.preventDefault()}
      onClick={onPick}
      onMouseMove={onHover}
    >
      <span>{option.label}</span>
      {option.group && <small aria-hidden="true">{option.group}</small>}
    </div>
  );
}
