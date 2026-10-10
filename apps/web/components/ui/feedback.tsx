import type { ComponentProps, ReactNode } from "react";

import { Button } from "./button";
import { cn } from "./cn";

// A message at the top of a form or page: an error in the design's error text (.ferr), being offline as a hint.
export function Banner({
  tone = "error",
  role,
  className,
  ...props
}: ComponentProps<"div"> & { tone?: "error" | "offline" }) {
  return (
    <div
      {...props}
      role={role ?? (tone === "error" ? "alert" : "status")}
      className={cn(tone === "error" ? "ferr" : "hint", className)}
    />
  );
}

// A page that could not load: what went wrong, and a button to try again.
export function RetryBanner({
  children,
  onRetry,
  className,
}: {
  children: ReactNode;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <div className={cn("bar", className)}>
      <Banner>{children}</Banner>
      <Button tone="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

// "Fix the highlighted fields" summary shown above a form that failed validation.
export function ErrorSummary({ count }: { count: number }) {
  if (!count) return null;
  return (
    <Banner>
      {count === 1
        ? "Fix the highlighted field to save."
        : `Fix the ${count} highlighted fields to save.`}
    </Banner>
  );
}

// A short explanation inside a form, in the design's hint type. A limit is gold, information slate.
export function Note({
  tone = "warn",
  className,
  ...props
}: ComponentProps<"p"> & { tone?: "warn" | "info" }) {
  return (
    <p
      {...props}
      className={cn("hint", tone === "warn" && "text-gold", className)}
    />
  );
}

const STATUS = {
  ok: "ok",
  warn: "wait",
  off: "bad",
  neutral: "mute",
} as const;

// A state in a list (.chip ok|wait|bad|mute).
export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: keyof typeof STATUS;
  children: ReactNode;
}) {
  return <span className={cn("chip", STATUS[tone])}>{children}</span>;
}

// A plain label in a list (.chip mute), such as the source of an expense.
export function PlainTag({ children }: { children: ReactNode }) {
  return <span className="chip mute">{children}</span>;
}

// Running total against a target, e.g. an allocation: slate while it adds up, clay when it does not (.hint.neg).
export function BalancePanel({
  ok,
  className,
  ...props
}: ComponentProps<"div"> & { ok: boolean }) {
  return (
    <div
      role="status"
      {...props}
      className={cn(
        "hint bal flex flex-wrap justify-between gap-3",
        !ok && "neg",
        className,
      )}
    />
  );
}
