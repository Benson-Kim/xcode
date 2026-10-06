import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

const PILL =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full border-2 px-5 text-[15px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50";

// Colour backs up what the button does, as in the design (.btn-pill): green to save or add, amber to turn off, stop
// or pause, red to remove or block, plain grey to cancel or go back. Blue is for the main action that is none of those.
const TONES = {
  primary:
    "border-blue bg-blue text-on-fill hover:enabled:border-blue-dark hover:enabled:bg-blue-dark aria-busy:bg-blue-busy",
  outline: "border-blue bg-transparent text-blue hover:enabled:bg-blue-tint",
  ok: "border-green bg-green text-on-fill hover:enabled:border-green-dark hover:enabled:bg-green-dark aria-busy:opacity-80",
  warn: "border-amber bg-amber-bg text-amber-text hover:enabled:bg-amber-hover",
  danger: "border-red bg-red-bg text-red-text hover:enabled:bg-red-hover",
  quiet: "border-line bg-transparent text-grey hover:enabled:bg-hover hover:enabled:text-navy",
} as const;

// pill button .
export function Button({
  tone = "primary",
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { tone?: keyof typeof TONES }) {
  return (
    <button
      {...props}
      type={type}
      className={cn(PILL, TONES[tone], className)}
    />
  );
}

// A pill button that opens the file picker.
export function FileButton({
  tone = "outline",
  accept,
  disabled,
  onFile,
  children,
}: {
  tone?: keyof typeof TONES;
  accept: string;
  disabled?: boolean;
  onFile: (file: File) => void;
  children: ReactNode;
}) {
  return (
    <label
      className={cn(
        PILL,
        TONES[tone],
        "cursor-pointer focus-within:outline-3 focus-within:outline-offset-2 focus-within:outline-blue/45",
        disabled && "pointer-events-none opacity-50",
      )}
    >
      {children}
      <input
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) onFile(file);
        }}
      />
    </label>
  );
}

// Quick picks and bulk actions
export function Chip({
  className,
  type = "button",
  ...props
}: ComponentProps<"button">) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "min-h-9 rounded-full border border-line bg-surface px-3.5 text-sm font-semibold text-navy hover:enabled:border-blue hover:enabled:text-blue-dark disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    />
  );
}

export function ChipGroup({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("flex flex-wrap gap-2", className)} />;
}

// Text-only action. "start"/"end" drop the padding on that side to align with the column edge;
// `compact` is the shorter version that sits beside a field label.
export function LinkButton({
  align,
  compact = false,
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { align?: "start" | "end"; compact?: boolean }) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        compact ? "min-h-9" : "min-h-11",
        "px-2 text-[15px] font-semibold text-blue hover:enabled:text-blue-dark hover:enabled:underline disabled:cursor-default disabled:font-medium disabled:text-grey",
        align === "start" && "pl-0",
        align === "end" && "pr-0",
        className,
      )}
    />
  );
}

// The linked first cell of a list row
export function RowButton({
  className,
  type = "button",
  ...props
}: ComponentProps<"button">) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "min-h-8 p-0 text-left text-[15px] font-bold text-blue hover:underline",
        className,
      )}
    />
  );
}

export function IconButton({
  className,
  type = "button",
  ...props
}: ComponentProps<"button">) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "grid size-11 shrink-0 place-items-center rounded-[10px] text-navy hover:enabled:bg-hover disabled:cursor-default disabled:opacity-35",
        className,
      )}
    />
  );
}

// The action at the foot of a card
export function CardAction({
  primary = false,
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { primary?: boolean }) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "mt-1.5 min-h-11 self-start rounded-full border-2 border-blue px-5 text-[15px] font-semibold",
        primary
          ? "bg-blue text-on-fill hover:bg-blue-dark"
          : "bg-transparent text-blue hover:bg-blue-tint",
        className,
      )}
    />
  );
}
