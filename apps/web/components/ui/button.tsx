import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

// Colour backs up what the button does (.btn): ink for the page's main action, teal to save or confirm, gold to turn
// off or pause, clay to remove or block, white to cancel or go back. On the hero the design turns them to glass.
const TONES = {
  primary: "btn pri",
  outline: "btn",
  ok: "btn ok",
  warn: "btn warn",
  danger: "btn bad",
  quiet: "act plain",
} as const;

const SIZES = {
  sm: "sm",
} as const;

export function Button({
  tone = "primary",
  size,
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & {
  tone?: keyof typeof TONES;
  size?: keyof typeof SIZES;
}) {
  return (
    <button
      {...props}
      type={type}
      className={cn(TONES[tone], size && SIZES[size], className)}
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
        TONES[tone],
        "focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-teal",
        disabled && "pointer-events-none opacity-45",
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

// Quick picks and bulk actions, inside a ChipGroup (.quick button).
export function Chip({
  className,
  type = "button",
  ...props
}: ComponentProps<"button">) {
  return (
    <button
      {...props}
      type={type}
      className={cn("disabled:cursor-default disabled:opacity-45", className)}
    />
  );
}

const ACT_TONES = {
  plain: "plain",
  ok: "ok",
  warn: "warn",
  bad: "bad",
} as const;

// A row's own action (.act): no border, smaller and quieter than the page's pill buttons, coloured the same way.
// With no tone it is ink, as Edit is in the design.
export function RowAction({
  tone,
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { tone?: keyof typeof ACT_TONES }) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "act disabled:cursor-default disabled:opacity-45",
        tone && ACT_TONES[tone],
        className,
      )}
    />
  );
}

// The actions at the end of a row (.tacts).
export function RowActionGroup({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("tacts", className)} />;
}

export function ChipGroup({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("quick", className)} />;
}

// Text-only action: `compact` beside a field label in a form (.mlink), otherwise a link under a form (.linkb).
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
      data-align={align}
      className={cn(
        compact ? "mlink" : "linkb",
        "disabled:cursor-default disabled:text-slate",
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
        "border-0 bg-transparent p-0 text-left font-semibold text-ink hover:text-teal hover:underline",
        className,
      )}
    />
  );
}

// A square icon button, the size of the design's step buttons. `remove` is the clay cross of a split row (.rmx).
export function IconButton({
  variant,
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { variant?: "remove" }) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        variant === "remove"
          ? "rmx"
          : "grid size-[34px] shrink-0 place-items-center rounded-[9px] border-0 bg-transparent text-ink hover:enabled:bg-paper",
        "disabled:cursor-default disabled:opacity-30",
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
      className={cn(primary ? "btn pri" : "btn", "self-start", className)}
    />
  );
}
