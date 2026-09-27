import type { ComponentProps } from "react";
import { cn } from "./cn";

const PILL =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full border-2 px-5 text-[15px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50";

const TONES = {
  primary: "border-blue bg-blue text-white hover:enabled:border-blue-dark hover:enabled:bg-blue-dark aria-busy:bg-blue-busy",
  outline: "border-blue bg-transparent text-blue hover:enabled:bg-blue-tint",
  danger: "border-red bg-transparent text-red hover:enabled:bg-red-bg",
} as const;

// The design's pill button (.btn-pill).
export function Button({
  tone = "primary",
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { tone?: keyof typeof TONES }) {
  return <button {...props} type={type} className={cn(PILL, TONES[tone], className)} />;
}

// Quick picks and bulk actions (.chip).
export function Chip({ className, type = "button", ...props }: ComponentProps<"button">) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "min-h-9 rounded-full border border-line bg-white px-3.5 text-sm font-semibold text-navy hover:enabled:border-blue hover:enabled:text-blue-dark disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    />
  );
}

export function ChipGroup({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("flex flex-wrap gap-2", className)} />;
}

// Text-only action (.link-btn). "start"/"end" drop the padding on that side to align with the column edge;
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

// The linked first cell of a list row (.row-btn).
export function RowButton({ className, type = "button", ...props }: ComponentProps<"button">) {
  return (
    <button
      {...props}
      type={type}
      className={cn("min-h-8 p-0 text-left text-[15px] font-bold text-blue hover:underline", className)}
    />
  );
}

export function IconButton({ className, type = "button", ...props }: ComponentProps<"button">) {
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

// The action at the foot of a card (.card-action).
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
        primary ? "bg-blue text-white hover:bg-blue-dark" : "bg-transparent text-blue hover:bg-blue-tint",
        className,
      )}
    />
  );
}
