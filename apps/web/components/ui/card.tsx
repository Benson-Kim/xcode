import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

// The white panel every screen is built from. Form cards space their fields a little wider.
export function Card({
  density = "standard",
  className,
  ...props
}: ComponentProps<"article"> & { density?: "standard" | "form" }) {
  return (
    <article
      {...props}
      className={cn(
        "flex min-w-0 flex-col rounded-[18px] border border-line bg-surface px-5 py-[18px]",
        density === "form" ? "gap-3.5" : "gap-2.5",
        className,
      )}
    />
  );
}

export function CardHeader({
  title,
  description,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  id?: string;
}) {
  return (
    <header className="flex flex-col gap-0.5">
      <h2 id={id} className="m-0 text-[17px] leading-[1.3] font-bold text-ink">
        {title}
      </h2>
      {description && (
        <p className="m-0 text-[13px] text-slate">{description}</p>
      )}
    </header>
  );
}

export function CardValue({
  tone,
  className,
  ...props
}: ComponentProps<"p"> & { tone?: "bad" }) {
  return (
    <p
      {...props}
      className={cn(
        "mt-1 mb-0 text-[30px] leading-[1.15] font-bold tabular-nums",
        tone === "bad" && "text-red",
        className,
      )}
    />
  );
}

export function CardNote({ className, ...props }: ComponentProps<"p">) {
  return <p {...props} className={cn("m-0 text-sm text-slate", className)} />;
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div
      className="h-[7px] overflow-hidden rounded-full bg-paper-2"
      aria-hidden="true"
    >
      <span
        className="block h-full rounded-full bg-teal-mid"
        style={{ width: `${Math.max(0, Math.min(value, 100))}%` }}
      />
    </div>
  );
}

// Label/value rows inside a card
export function CardList({ className, ...props }: ComponentProps<"ul">) {
  return <ul {...props} className={cn("mt-1 mb-0 list-none p-0", className)} />;
}

export function CardListItem({
  left,
  leftSub,
  right,
  rightSub,
  tone,
}: {
  left: ReactNode;
  leftSub?: ReactNode;
  right?: ReactNode;
  rightSub?: ReactNode;
  tone?: "bad";
}) {
  return (
    <li className="flex justify-between gap-3 border-t border-divider py-[9px]">
      <span className="flex min-w-0 flex-col">
        {typeof left === "string" ? (
          <strong className="text-[14.5px] font-semibold text-ink tabular-nums">
            {left}
          </strong>
        ) : (
          left
        )}
        {leftSub && <small className="text-[13px] text-slate">{leftSub}</small>}
      </span>
      {(right || rightSub) && (
        <span className="flex max-w-[60%] shrink-0 flex-col items-end text-right">
          {right && (
            <strong
              className={cn(
                "text-[14.5px] font-bold tabular-nums",
                tone === "bad" ? "text-red" : "text-ink",
              )}
            >
              {right}
            </strong>
          )}
          {rightSub && (
            <small className="text-[13px] text-slate">{rightSub}</small>
          )}
        </span>
      )}
    </li>
  );
}

// Report figures
export function StatGrid({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      {...props}
      className={cn(
        "grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3",
        className,
      )}
    />
  );
}

export function Stat({
  label,
  value,
  tone,
}: {
  label: ReactNode;
  value: ReactNode;
  tone?: "bad";
}) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <small className="block text-xs font-bold tracking-[.07em] text-slate uppercase">
        {label}
      </small>
      <strong
        className={cn(
          "text-lg tabular-nums",
          tone === "bad" ? "text-red" : "text-ink",
        )}
      >
        {value}
      </strong>
    </div>
  );
}
