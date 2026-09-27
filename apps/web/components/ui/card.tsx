import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";

// The white panel every screen is built from (.card). Form cards space their fields a little wider.
export function Card({
  density = "standard",
  className,
  ...props
}: ComponentProps<"article"> & { density?: "standard" | "form" }) {
  return (
    <article
      {...props}
      className={cn(
        "flex min-w-0 flex-col rounded-[14px] border border-card-line bg-white p-5",
        density === "form" ? "gap-3.5" : "gap-2.5",
        className,
      )}
    />
  );
}

export function CardHeader({ title, description, id }: { title: ReactNode; description?: ReactNode; id?: string }) {
  return (
    <header className="flex flex-col gap-0.5">
      <h2 id={id} className="m-0 text-base leading-[1.3] font-bold">
        {title}
      </h2>
      {description && <p className="m-0 text-[13px] text-grey">{description}</p>}
    </header>
  );
}

export function CardValue({ tone, className, ...props }: ComponentProps<"p"> & { tone?: "bad" }) {
  return (
    <p
      {...props}
      className={cn("mt-1 mb-0 text-[30px] leading-[1.15] font-bold tabular-nums", tone === "bad" && "text-red", className)}
    />
  );
}

export function CardNote({ className, ...props }: ComponentProps<"p">) {
  return <p {...props} className={cn("m-0 text-sm text-grey", className)} />;
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-divider" aria-hidden="true">
      <span className="block h-full rounded-full bg-blue" style={{ width: `${Math.max(0, Math.min(value, 100))}%` }} />
    </div>
  );
}

// Label/value rows inside a card (.card-list).
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
    <li className="flex justify-between gap-3 border-t border-divider py-2.5">
      <span className="flex min-w-0 flex-col">
        {typeof left === "string" ? <strong className="text-[15px] font-semibold tabular-nums">{left}</strong> : left}
        {leftSub && <small className="text-[13px] text-grey">{leftSub}</small>}
      </span>
      {(right || rightSub) && (
        <span className="flex max-w-[60%] shrink-0 flex-col items-end text-right">
          {right && <strong className={cn("text-[15px] font-semibold tabular-nums", tone === "bad" && "text-red")}>{right}</strong>}
          {rightSub && <small className="text-[13px] text-grey">{rightSub}</small>}
        </span>
      )}
    </li>
  );
}

// Report figures (.report-grid / .stat).
export function StatGrid({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3", className)} />;
}

export function Stat({ label, value, tone }: { label: ReactNode; value: ReactNode; tone?: "bad" }) {
  return (
    <div className="rounded-[10px] border border-divider p-3">
      <small className="block text-[13px] text-grey">{label}</small>
      <strong className={cn("text-lg tabular-nums", tone === "bad" && "text-red")}>{value}</strong>
    </div>
  );
}
