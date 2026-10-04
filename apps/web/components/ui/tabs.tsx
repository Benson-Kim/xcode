import type { KeyboardEvent, ReactNode } from "react";

// Button cards at the top of a screen that show one part of it at a time (.tabs). Arrow keys, Home and End move
// between them; the chosen part is the tab panel below.
export function Tabs<T extends string>({
  id,
  label,
  options,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  children: ReactNode;
}) {
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = options.length - 1;
    const next =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    onChange(options[next].value);
    document.getElementById(`${id}-tab-${options[next].value}`)?.focus();
  }
  return (
    <>
      <div role="tablist" aria-label={label} className="mt-4.5 flex flex-wrap gap-2">
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
            className="min-h-11 rounded-xl border border-card-line bg-white px-4.5 text-[15px] font-semibold text-navy hover:border-blue hover:text-blue-dark aria-selected:border-2 aria-selected:border-blue aria-selected:bg-blue-soft aria-selected:text-blue-dark"
          >
            {option.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${value}`}>
        {children}
      </div>
    </>
  );
}
