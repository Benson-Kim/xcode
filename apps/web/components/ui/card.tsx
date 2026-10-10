import type { ComponentProps, ReactNode } from "react";

import { cn } from "./cn";

// The white panel every screen is built from (.card). Its parts stack; form cards space their fields a little wider.
export function Card({
  density = "standard",
  className,
  ...props
}: ComponentProps<"article"> & { density?: "standard" | "form" }) {
  return (
    <article
      {...props}
      className={cn(
        "card flex flex-col",
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
  // The card's own gap stands in for most of the design's space under the heading.
  return (
    <header className="ch mb-1">
      <div>
        <h2 id={id}>{title}</h2>
        {description && <p className="sub">{description}</p>}
      </div>
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

// A bar of how far along something is (.prog .t), teal once it is full.
export function ProgressBar({ value }: { value: number }) {
  const width = Math.max(0, Math.min(value, 100));
  return (
    <div className="prog min-w-0" aria-hidden="true">
      <div className="t">
        <i
          className={cn(width >= 100 && "full")}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

// Label/value rows inside a card (.lines .ln)
export function CardList({ className, ...props }: ComponentProps<"ul">) {
  return <ul {...props} className={cn("lines", className)} />;
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
    <li className="ln">
      <span className="l">
        {left}
        {leftSub && <span className="muted">{leftSub}</span>}
      </span>
      {(right || rightSub) && (
        <span className="max-w-[60%] shrink-0 text-right">
          {right && <b className={cn(tone === "bad" && "neg")}>{right}</b>}
          {rightSub && <small className="muted block">{rightSub}</small>}
        </span>
      )}
    </li>
  );
}

// Report figures: label over value, labelled as the design's summary strip (.msum) is, on a white tile.
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
    <div className="rounded-xl border border-line bg-surface px-4 py-2.5">
      <small className="block text-[11.5px] font-bold tracking-[.06em] text-slate uppercase">
        {label}
      </small>
      <strong
        className={cn(
          "text-[17px] tabular-nums",
          tone === "bad" ? "text-red" : "text-ink",
        )}
      >
        {value}
      </strong>
    </div>
  );
}
