import type { KeyboardEvent, ReactNode } from "react";

// Button cards at the top of a screen that show one part of it at a time.
// Arrow keys, Home and End move between them; the chosen part is the tab panel below.
// With `aside` the buttons stack beside it (.pc-top), and the up and down arrows move between them too.
export function Tabs<T extends string>({
  id,
  label,
  options,
  value,
  onChange,
  aside,
  children,
}: {
  id: string;
  label: string;
  options: { value: T; label: string }[];
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
      className={
        stacked
          ? "flex min-w-40 flex-col gap-2 max-[900px]:flex-row"
          : "mt-4.5 grid grid-cols-2 gap-3 max-[520px]:grid-cols-1"
      }
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
          className={`rounded-[18px] border border-line bg-surface px-[18px] py-3.5 text-left text-[14.5px] font-bold text-ink hover:border-teal-lift aria-selected:border-teal aria-selected:bg-teal-wash${stacked ? " flex-1" : ""}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
  return (
    <>
      {stacked ? (
        <div className="mt-4.5 flex items-stretch gap-3.5 max-[900px]:flex-col">
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
      >
        {children}
      </div>
    </>
  );
}
