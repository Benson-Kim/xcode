import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

const PILL =
  "inline-flex items-center justify-center gap-2 rounded-full border px-[18px] py-[9px] text-[14.5px] font-bold whitespace-nowrap transition-colors disabled:cursor-default disabled:opacity-45";

const SIZES = {
  sm: "px-[13px] py-1.5 text-[13px]",
} as const;

// Colour backs up what the button does: ink for the page's main action, teal to save or confirm, gold to turn off
// or pause, clay to remove or block, white to cancel or go back. Inside the hero band the same tones sit on glass.
const TONES = {
  primary:
    "border-ink bg-ink text-on-fill hover:enabled:border-ink-2 hover:enabled:bg-ink-2 aria-busy:opacity-80 [.hero_&]:border-white [.hero_&]:bg-white [.hero_&]:text-deep [.hero_&]:hover:enabled:border-paper-2 [.hero_&]:hover:enabled:bg-paper-2",
  outline:
    "border-line bg-surface text-ink hover:enabled:bg-paper [.hero_&]:border-glass-line [.hero_&]:bg-glass [.hero_&]:text-white [.hero_&]:hover:enabled:bg-glass-2",
  ok: "border-teal bg-teal text-on-fill hover:enabled:border-teal-dark hover:enabled:bg-teal-dark aria-busy:opacity-80 [.hero_&]:border-teal-bright [.hero_&]:bg-teal-bright [.hero_&]:text-deep [.hero_&]:hover:enabled:border-teal-lift [.hero_&]:hover:enabled:bg-teal-lift",
  warn: "border-gold-pure bg-gold-wash text-gold hover:enabled:bg-gold-pure hover:enabled:text-ink",
  danger:
    "border-clay bg-clay text-on-fill hover:enabled:border-clay-dark hover:enabled:bg-clay-dark",
  quiet:
    "border-transparent bg-transparent text-slate hover:enabled:bg-paper hover:enabled:text-ink [.hero_&]:text-on-deep [.hero_&]:hover:enabled:bg-glass",
} as const;

// pill button (.btn)
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
      className={cn(PILL, TONES[tone], size && SIZES[size], className)}
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
        "cursor-pointer focus-within:outline-3 focus-within:outline-offset-2 focus-within:outline-teal/45",
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
        "rounded-full border border-line bg-surface px-3.5 py-1.5 text-[13px] font-bold text-ink hover:enabled:border-teal-lift hover:enabled:bg-paper disabled:cursor-default disabled:opacity-45",
        className,
      )}
    />
  );
}

const ACT_TONES = {
  plain: "text-slate hover:enabled:bg-paper",
  ok: "text-teal hover:enabled:bg-teal-wash",
  warn: "text-gold hover:enabled:bg-gold-wash",
  bad: "text-clay hover:enabled:bg-clay-wash",
} as const;

// A row's own action (.act): no border, smaller and quieter than the page's pill buttons, coloured the same way.
export function RowAction({
  tone = "plain",
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { tone?: keyof typeof ACT_TONES }) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "rounded-lg px-[9px] py-[5px] text-[13px] font-bold whitespace-nowrap text-ink hover:enabled:bg-paper-2 disabled:cursor-default disabled:opacity-45",
        ACT_TONES[tone],
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
        "px-2 text-[14.5px] font-bold text-teal hover:enabled:text-teal-dark hover:enabled:underline disabled:cursor-default disabled:font-medium disabled:text-slate",
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
        "min-h-8 p-0 text-left text-[14.5px] font-bold text-ink hover:text-teal hover:underline",
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
        "grid size-11 shrink-0 place-items-center rounded-[10px] text-ink hover:enabled:bg-paper-2 disabled:cursor-default disabled:opacity-35",
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
        "mt-1.5 self-start rounded-full border px-[18px] py-[9px] text-[14.5px] font-bold",
        primary
          ? "border-ink bg-ink text-on-fill hover:bg-ink-2"
          : "border-line bg-surface text-ink hover:bg-paper",
        className,
      )}
    />
  );
}
