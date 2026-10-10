"use client";

import {
  createContext,
  useContext,
  useId,
  type ComponentProps,
  type ReactNode,
} from "react";

import { useFormats } from "../../lib/formats";
import { cn } from "./cn";

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
    <p id={id} role="alert" className="ferr">
      {children}
    </p>
  );
}

// A labelled control with its hint and error (.f > label + .inp). An action beside the label puts both in a .flabrow.
// The control inside picks up the id, the describing hint/error and the invalid state automatically.
export function Field({
  id,
  label,
  action,
  hint,
  error,
  className,
  children,
}: {
  id: string;
  label: ReactNode;
  action?: ReactNode;
  hint?: ReactNode;
  error?: string;
  className?: string;
  children: ReactNode;
}) {
  const describedBy =
    [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ") ||
    undefined;
  return (
    <div className={cn("f", className)}>
      {action ? (
        <div className="flabrow">
          <label htmlFor={id}>{label}</label>
          {action}
        </div>
      ) : (
        <label htmlFor={id}>{label}</label>
      )}
      <FieldContext.Provider
        value={{ id, describedBy, invalid: Boolean(error) }}
      >
        {children}
      </FieldContext.Provider>
      {hint && (
        <p id={`${id}-hint`} className="hint">
          {hint}
        </p>
      )}
      {error && <ErrorText id={`${id}-error`}>{error}</ErrorText>}
    </div>
  );
}

export function useFieldProps<
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

// The design's control (.inp), red when invalid (.err). Its size comes from where it sits (a pop up, a bar, the
// headline card), so both densities draw the same.
const DENSITY = {
  standard: "",
  compact: "",
} as const;

const isInvalid = (value: ComponentProps<"input">["aria-invalid"]) =>
  value !== undefined && value !== false && value !== "false";

export function controlClass(
  invalid: ComponentProps<"input">["aria-invalid"],
  ...rest: (string | false | null | undefined)[]
) {
  return cn("inp", isInvalid(invalid) && "err", ...rest);
}

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
  const field = useFieldProps(props);
  return (
    <input
      {...field}
      className={controlClass(
        field["aria-invalid"],
        DENSITY[density],
        inline && "w-auto max-w-full",
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
  const field = useFieldProps(props);
  return (
    <select
      {...field}
      className={controlClass(
        field["aria-invalid"],
        DENSITY[density],
        inline && "w-auto max-w-full",
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
  currency,
  density = "standard",
  className,
  value,
  onChange,
  ...props
}: ComponentProps<"input"> & {
  currency?: string;
  density?: keyof typeof DENSITY;
}) {
  const { currencyCode } = useFormats();
  const field = useFieldProps(props);
  return (
    <div className="flex w-full min-w-0 items-stretch">
      <span className="flex shrink-0 items-center rounded-l-[10px] border border-r-0 border-line bg-paper px-3 font-semibold text-slate">
        {currency ?? currencyCode()}
      </span>
      <input
        type="text"
        inputMode="decimal"
        autoComplete="off"
        {...field}
        value={groupThousands(value)}
        onChange={(event) => {
          const plain = event.target.value
            .replace(/[^0-9.]/g, "")
            .replace(/(\..*)\./g, "$1");
          event.target.value = plain;
          onChange?.(event);
        }}
        className={controlClass(
          field["aria-invalid"],
          "num",
          DENSITY[density],
          "flex-1 rounded-l-none",
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
        className="inp w-14 shrink-0 cursor-pointer p-1 disabled:cursor-default"
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

// A set of radio buttons or checkboxes laid out in a row (.checks)
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
    <div role={role} aria-label={label} className={cn("checks", className)}>
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
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy =
    [hint && hintId, error && errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="f">
      <span id={id} className="flab">
        {label}
      </span>
      <div
        role={role}
        aria-labelledby={id}
        aria-describedby={describedBy}
        className="checks"
      >
        {children}
      </div>
      {hint && (
        <p id={hintId} className="hint">
          {hint}
        </p>
      )}
      {error && <ErrorText id={errorId}>{error}</ErrorText>}
    </div>
  );
}

// One radio button or checkbox with its label (.ck)
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
      className={cn("ck cursor-pointer has-disabled:cursor-default", className)}
    >
      <input {...props} type={type} className="peer shrink-0" />
      <span className="peer-disabled:text-slate">
        {label}
        {description && (
          <small className="hint block font-medium">{description}</small>
        )}
      </span>
    </label>
  );
}

// Groups choices under a company or section name (.cogrp)
export function GroupLabel({ className, ...props }: ComponentProps<"p">) {
  return <p {...props} className={cn("cogrp", className)} />;
}

// Marks a change against a default (.chip)
export function Tag({
  tone,
  children,
}: {
  tone: "add" | "remove";
  children: ReactNode;
}) {
  return (
    <>
      {" "}
      <span className={cn("chip", tone === "add" ? "ok" : "bad")}>
        {children}
      </span>
    </>
  );
}

// Two fields side by side in a pop up (.mrow2); one column on a phone.
export function FieldPair({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("mrow2", className)} />;
}

// As many field columns as fit (.fgrid).
export function FieldGrid({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("fgrid", className)} />;
}

// A heading row between parts of a form, with a rule above it (.sect).
export function FormSection({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("sect", className)} />;
}

// The total of a pop up form on the brand colour (.mtot): label left, amount right.
export function FormTotal({
  label,
  value,
}: {
  label: ReactNode;
  value: ReactNode;
}) {
  return (
    <div className="mtot">
      <span>{label}</span>
      <b className="num">{value}</b>
    </div>
  );
}
