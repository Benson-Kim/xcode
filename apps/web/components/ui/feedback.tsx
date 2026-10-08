import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";
import { AlertIcon, OfflineIcon } from "./icons";

const BANNER = {
  error: "border-red-line bg-red-bg text-red-text",
  offline: "border-amber-line bg-amber-bg text-amber-text",
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
        "flex items-start gap-2.5 rounded-xl border px-3.5 py-3 text-[15px]",
        BANNER[tone],
        className,
      )}
    >
      <Icon size={18} className="mt-0.5 shrink-0" />
      <span>{children}</span>
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
        "m-0 rounded-[10px] px-3 py-2.5 text-sm",
        tone === "info"
          ? "bg-blue-soft text-blue-dark"
          : "bg-amber-bg text-amber-text",
        className,
      )}
    />
  );
}

const STATUS = {
  ok: "bg-green-bg text-green",
  warn: "bg-amber-bg text-amber-text",
  off: "bg-red-bg text-red-text",
  neutral: "bg-divider text-navy",
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
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[13px] font-semibold whitespace-nowrap",
        "before:size-1.75 before:rounded-full before:bg-current before:content-['']",
        STATUS[tone],
      )}
    >
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
        "flex flex-wrap justify-between gap-3 rounded-[10px] p-3 font-bold",
        ok ? "bg-green-bg text-green" : "bg-red-bg text-red-text",
        className,
      )}
    />
  );
}
