import type { ComponentProps, ReactNode } from "react";

import { Button } from "./button";
import { cn } from "./cn";
import { AlertIcon, OfflineIcon } from "./icons";

const BANNER = {
  error: "border-transparent bg-clay-wash text-clay",
  offline: "border-transparent bg-gold-wash text-gold",
} as const;

// A message across the top of a form or page (.banner).
export function Banner({
  tone = "error",
  role,
  className,
  children,
  ...props
}: ComponentProps<"div"> & { tone?: keyof typeof BANNER }) {
  const Icon = tone === "offline" ? OfflineIcon : AlertIcon;
  return (
    <div
      {...props}
      role={role ?? (tone === "error" ? "alert" : "status")}
      className={cn(
        "flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-[14.5px] font-semibold",
        BANNER[tone],
        className,
      )}
    >
      <Icon size={18} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
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
    <div className={cn("flex flex-wrap items-center gap-3", className)}>
      <Banner>{children}</Banner>
      <Button tone="outline" onClick={onRetry}>
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

// A short explanation inside a form (.note): amber for limits, blue for information.
export function Note({
  tone = "warn",
  className,
  ...props
}: ComponentProps<"p"> & { tone?: "warn" | "info" }) {
  return (
    <p
      {...props}
      className={cn(
        "m-0 rounded-xl px-3.5 py-2.5 text-sm font-semibold",
        tone === "info" ? "bg-teal-wash text-teal" : "bg-gold-wash text-gold",
        className,
      )}
    />
  );
}

const STATUS = {
  ok: "bg-teal-wash text-teal",
  warn: "bg-gold-wash text-gold",
  off: "bg-clay-wash text-clay",
  neutral: "bg-paper-2 text-ink-2",
} as const;

// A dot-and-label state in a list (.status).
export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: keyof typeof STATUS;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-bold whitespace-nowrap",
        "before:size-1.75 before:rounded-full before:bg-current before:content-['']",
        STATUS[tone],
      )}
    >
      {children}
    </span>
  );
}

// A plain label in a list, with no indicator (the source of an expense).
export function PlainTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded-full bg-paper-2 px-2.5 py-0.5 text-xs font-bold whitespace-nowrap text-ink-2">
      {children}
    </span>
  );
}

// Running total against a target, e.g. an allocation (.balance).
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
        "flex flex-wrap justify-between gap-3 rounded-xl p-3 font-bold",
        ok ? "bg-teal-wash text-teal" : "bg-clay-wash text-clay",
        className,
      )}
    />
  );
}
