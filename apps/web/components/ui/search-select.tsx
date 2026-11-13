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

import { rankOptions } from "@xcode/shared/search";

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

function useMatching(options: readonly SearchOption[], query: string | null) {
  return useMemo(() => rankOptions(query ?? "", options), [options, query]);
}

// A dropdown that can be searched, as the design's item search (comboHtml): a combobox (.inp) over a listbox
// (.combolist), each option (.copt) with its group in small type beside it. The list floats over the rows and fields
// below it, so a dropdown in a table row or a form never pushes them down or gets clipped. Typing ranks the
// options, best match first, the arrow keys move through them (the highlighted one is aria-selected), Enter or Tab
// takes it, Escape closes. A click or a tap takes an option too. Given onAdd, "+ Add new" is the last option: it
// hands over what was typed, so the caller can open its create form with it.
export function SearchSelect({
  options,
  value,
  onChange,
  onAdd,
  addLabel = "Add new",
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
  onAdd?: (typed: string) => void;
  addLabel?: string;
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
  const box = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const combo = useCombo({ options, value, onChange, onAdd, box, list });
  const { open, query, listId } = combo;

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
        aria-activedescendant={combo.activeId}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        placeholder={placeholder}
        value={open && query !== null ? query : (combo.chosen?.label ?? "")}
        onFocus={(event) => {
          event.target.select();
          combo.show();
        }}
        onClick={() => !open && combo.show()}
        onChange={(event) => combo.type(event.target.value)}
        onBlur={combo.close}
        onKeyDown={combo.onKeyDown}
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
        id={listId}
        open={open}
        shown={combo.shown}
        active={combo.active}
        emptyText={emptyText}
        onPick={combo.pick}
        onHover={combo.setActive}
        add={
          onAdd && {
            label: `+ ${addLabel}`,
            typed: (query ?? "").trim(),
            onPick: combo.add,
          }
        }
      />
    </div>
  );
}

// The open state, the query and the highlighted option of a SearchSelect, and what its keys do.
function useCombo({
  options,
  value,
  onChange,
  onAdd,
  box,
  list,
}: {
  options: readonly SearchOption[];
  value: string;
  onChange: (value: string) => void;
  onAdd?: (typed: string) => void;
  box: RefObject<HTMLDivElement | null>;
  list: RefObject<HTMLDivElement | null>;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  const chosen = options.find((option) => option.value === value);
  const shown = useMatching(options, query);
  const addAt = onAdd ? shown.length : -1;
  const count = shown.length + (onAdd ? 1 : 0);

  const optionId = (index: number) => `${listId}-${index}`;
  const activeId = open && active < count ? optionId(active) : undefined;
  useAnchoredPosition(open, box, list, { gap: 6, matchWidth: true });

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

  function add() {
    const typed = (query ?? "").trim();
    close();
    onAdd?.(typed);
  }

  function take() {
    if (active === addAt) add();
    else pick(shown[active]);
  }

  function move(step: number) {
    if (!open) return show();
    if (count) setActive((at) => (at + step + count) % count);
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
        return setActive(event.key === "Home" ? 0 : count - 1);
      case "Enter":
        if (!open) return;
        event.preventDefault();
        return take();
      case "Tab":
        if (open && query !== null && active !== addAt) pick(shown[active]);
        else close();
        return;
      case "Escape":
        if (!open) return;
        event.preventDefault();
        event.stopPropagation();
        return close();
    }
  }

  return {
    listId,
    open,
    query,
    active,
    setActive,
    shown,
    chosen,
    activeId,
    show,
    type,
    close,
    pick,
    add,
    onKeyDown,
  };
}

function Listbox({
  listRef,
  id,
  open,
  shown,
  active,
  emptyText,
  onPick,
  onHover,
  add,
}: {
  listRef: RefObject<HTMLDivElement | null>;
  id: string;
  open: boolean;
  shown: readonly SearchOption[];
  active: number;
  emptyText: string;
  onPick: (option: SearchOption) => void;
  onHover: (index: number) => void;
  add?: { label: string; typed: string; onPick: () => void };
}) {
  const addAt = shown.length;
  return (
    <div
      ref={listRef}
      id={id}
      role="listbox"
      hidden={!open}
      className="combolist fixed min-w-44"
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
      {add && (
        <Option
          id={`${id}-${addAt}`}
          option={{ value: "", label: add.label }}
          note={add.typed}
          highlighted={addAt === active}
          className="sticky bottom-0 border-t border-line bg-(--shell) text-teal"
          onPick={add.onPick}
          onHover={() => onHover(addAt)}
        />
      )}
    </div>
  );
}

function Option({
  id,
  option,
  note,
  highlighted,
  className,
  onPick,
  onHover,
}: {
  id: string;
  option: SearchOption;
  note?: string;
  highlighted: boolean;
  className?: string;
  onPick: () => void;
  onHover: () => void;
}) {
  const aside = note ?? option.group;
  return (
    <div
      id={id}
      role="option"
      aria-selected={highlighted}
      className={cn("copt cursor-pointer", className)}
      // The input keeps focus: a press on an option must not blur it before the click lands.
      onMouseDown={(event) => event.preventDefault()}
      onClick={onPick}
      onMouseMove={onHover}
    >
      <span>{option.label}</span>
      {aside && <small aria-hidden="true">{aside}</small>}
    </div>
  );
}
