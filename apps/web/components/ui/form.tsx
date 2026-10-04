"use client";

import {
  createContext,
  useContext,
  useId,
  type ComponentProps,
  type ReactNode,
} from "react";
import { cn } from "./cn";
import { AlertIcon } from "./icons";
import { currencyCode } from "../../lib/format";

type FieldWiring = { id: string; describedBy?: string; invalid: boolean };
const FieldContext = createContext<FieldWiring | null>(null);

export function ErrorText({
  id,
  children,
}: {
  id?: string;
  children: ReactNode;
}) {
  return (
    <p id={id} className="m-0 flex items-start gap-1.5 text-[13px] text-red">
      <AlertIcon className="mt-px shrink-0" />
      <span>{children}</span>
    </p>
  );
}

// A labelled control with its hint and error.
// The control inside picks up the id, the describing hint/error and the invalid state automatically.
export function Field({
  id,
  label,
  hint,
  error,
  className,
  children,
}: {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: string;
  className?: string;
  children: ReactNode;
}) {
  const describedBy =
    [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") ||
    undefined;
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      <FieldContext.Provider
        value={{ id, describedBy, invalid: Boolean(error) }}
      >
        {children}
      </FieldContext.Provider>
      {hint && (
        <p id={`${id}-hint`} className="m-0 text-[13px] text-grey">
          {hint}
        </p>
      )}
      {error && <ErrorText id={`${id}-error`}>{error}</ErrorText>}
    </div>
  );
}

function useFieldProps<
  T extends {
    id?: string;
    "aria-describedby"?: string;
    "aria-invalid"?: ComponentProps<"input">["aria-invalid"];
  },
>(props: T) {
  const field = useContext(FieldContext);
  return {
    ...props,
    id: props.id ?? field?.id,
    "aria-describedby": props["aria-describedby"] ?? field?.describedBy,
    "aria-invalid": props["aria-invalid"] ?? (field?.invalid || undefined),
  };
}

const CONTROL =
  "rounded-[10px] border border-line bg-white px-3 text-navy placeholder:text-grey/70 focus:border-blue focus:outline-3 focus:outline-offset-1 focus:outline-blue/30 aria-invalid:border-2 aria-invalid:border-red disabled:bg-hover disabled:text-grey";
const DENSITY = {
  standard: "h-12 text-base",
  compact: "h-11 text-[15px]",
} as const;

// `inline` sizes the control to its content (in a toolbar) instead of filling its column. It still may not
// outgrow the toolbar: a select is as wide as its longest option, and one long company name would otherwise
// push the page sideways.
export function TextInput({
  density = "standard",
  inline = false,
  className,
  ...props
}: ComponentProps<"input"> & {
  density?: keyof typeof DENSITY;
  inline?: boolean;
}) {
  return (
    <input
      {...useFieldProps(props)}
      className={cn(
        CONTROL,
        DENSITY[density],
        inline ? "w-auto min-w-0 max-w-full" : "w-full",
        className,
      )}
    />
  );
}

export function SelectInput({
  density = "standard",
  inline = false,
  className,
  ...props
}: ComponentProps<"select"> & {
  density?: keyof typeof DENSITY;
  inline?: boolean;
}) {
  return (
    <select
      {...useFieldProps(props)}
      className={cn(
        CONTROL,
        DENSITY[density],
        inline ? "w-auto min-w-0 max-w-full" : "w-full",
        className,
      )}
    />
  );
}

function groupThousands(value: ComponentProps<"input">["value"]) {
  const [whole, fraction] = String(value ?? "").split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return fraction === undefined ? grouped : `${grouped}.${fraction}`;
}

// An amount with its currency in front. It shows thousands separators while typing
// onChange receives the plain number text (e.g. "49000.50").
export function CurrencyInput({
  currency = currencyCode(),
  density = "standard",
  className,
  value,
  onChange,
  ...props
}: ComponentProps<"input"> & {
  currency?: string;
  density?: keyof typeof DENSITY;
}) {
  return (
    <div className="flex w-full min-w-0 items-stretch">
      <span className="flex shrink-0 items-center rounded-l-[10px] border border-r-0 border-line bg-paper px-3 text-[15px] text-grey">
        {currency}
      </span>
      <input
        type="text"
        inputMode="decimal"
        autoComplete="off"
        {...useFieldProps(props)}
        value={groupThousands(value)}
        onChange={(event) => {
          const plain = event.target.value
            .replace(/[^0-9.]/g, "")
            .replace(/(\..*)\./g, "$1");
          event.target.value = plain;
          onChange?.(event);
        }}
        className={cn(
          CONTROL,
          DENSITY[density],
          "w-full min-w-0 flex-1 rounded-l-none tabular-nums",
          className,
        )}
      />
    </div>
  );
}

// A six-digit hex colour with a swatch picker beside it. The text field takes the Field's id and error.
export function ColorInput({
  value,
  onChange,
  pickerLabel,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  pickerLabel: string;
  disabled?: boolean;
}) {
  const valid = /^#[0-9a-fA-F]{6}$/.test(value);
  return (
    <div className="flex min-w-0 items-stretch gap-2">
      <input
        type="color"
        aria-label={pickerLabel}
        value={valid ? value.toLowerCase() : "#000000"}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value.toUpperCase())}
        className="h-12 w-14 shrink-0 cursor-pointer rounded-[10px] border border-line bg-white p-1 disabled:cursor-default"
      />
      <TextInput
        value={value}
        maxLength={7}
        disabled={disabled}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

// A set of radio buttons or checkboxes laid out in a row
export function ChoiceGroup({
  label,
  role = "group",
  className,
  children,
}: {
  label?: string;
  role?: "group" | "radiogroup";
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      role={role}
      aria-label={label}
      className={cn("flex flex-wrap gap-x-5 gap-y-1", className)}
    >
      {children}
    </div>
  );
}

// A labelled group of choices with a visible label and hint, laid out like a field.
export function ChoiceField({
  label,
  hint,
  error,
  role = "radiogroup",
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  role?: "group" | "radiogroup";
  children: ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span id={id} className="text-sm font-semibold">
        {label}
      </span>
      <div
        role={role}
        aria-labelledby={id}
        className="flex flex-wrap gap-x-5 gap-y-1"
      >
        {children}
      </div>
      {hint && <p className="m-0 text-[13px] text-grey">{hint}</p>}
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}

// One radio button or checkbox with its label
export function Choice({
  label,
  description,
  className,
  type = "checkbox",
  ...props
}: Omit<ComponentProps<"input">, "type"> & {
  label: ReactNode;
  description?: ReactNode;
  type?: "checkbox" | "radio";
}) {
  return (
    <label
      className={cn(
        "flex min-h-11 cursor-pointer items-center gap-2.5 text-[15px] has-disabled:cursor-default",
        className,
      )}
    >
      <input
        {...props}
        type={type}
        className="peer m-0 size-5 shrink-0 accent-blue"
      />
      <span className="peer-disabled:text-grey">
        {label}
        {description && (
          <small className="block text-[13px] text-grey">{description}</small>
        )}
      </span>
    </label>
  );
}

// Groups choices under a company or section name
export function GroupLabel({ className, ...props }: ComponentProps<"p">) {
  return (
    <p
      {...props}
      className={cn("mt-2 mb-0 text-[13px] font-bold text-grey", className)}
    />
  );
}

// Marks a change against a default
export function Tag({
  tone,
  children,
}: {
  tone: "add" | "remove";
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "ml-1.5 rounded-md px-1.5 py-px text-xs font-bold whitespace-nowrap",
        tone === "add"
          ? "bg-blue-soft text-blue-dark"
          : "bg-red-bg text-red-text",
      )}
    >
      {children}
    </span>
  );
}
