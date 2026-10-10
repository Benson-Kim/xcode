"use client";

import {
  createContext,
  useContext,
  useEffect,
  type ComponentProps,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { cn } from "./cn";

// Where the app shell draws a page's title, actions and headline card: the brand zone above the working sheet.
// Without a shell (tests, the sign-in screen) a page keeps them inline.
export type HeroSlots = {
  title: HTMLElement | null;
  actions: HTMLElement | null;
  band: HTMLElement | null;
  // The profile button, carried by a headline card that replaces the title row (petty cash).
  profile?: ReactNode;
  hideHead?: (hidden: boolean) => void;
};
const HeroSlotsContext = createContext<HeroSlots | null>(null);
export const HeroSlotsProvider = HeroSlotsContext.Provider;

// Page title, subtitle and the page's own actions (.head). In the shell the actions sit left of the profile button.
export function PageHeader({
  title,
  description,
  actions,
  srOnlyTitle = false,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  srOnlyTitle?: boolean;
}) {
  const slots = useContext(HeroSlotsContext);
  const heading = (
    <header className={cn("min-w-0", srOnlyTitle && "sr-only")}>
      <h1>{title}</h1>
      {description && <p className="sub">{description}</p>}
    </header>
  );
  if (slots?.title)
    return (
      <>
        {createPortal(heading, slots.title)}
        {actions &&
          slots.actions &&
          createPortal(<div className="acts">{actions}</div>, slots.actions)}
      </>
    );
  return (
    <div className="mb-1 flex flex-wrap items-end justify-between gap-x-5 gap-y-3">
      <header className={cn("min-w-0", srOnlyTitle && "sr-only")}>
        <h1 className="m-0 text-[clamp(22px,1.9vw,26px)] leading-[1.1] font-extrabold tracking-[-0.02em] text-ink">
          {title}
        </h1>
        {description && (
          <p className="mt-1 mb-0 text-sm font-semibold text-slate">
            {description}
          </p>
        )}
      </header>
      {actions && (
        <div className="flex flex-wrap items-center gap-2.5">{actions}</div>
      )}
    </div>
  );
}

// The headline card (.band): the period control first, then the figures, then the tools at its right end (source,
// search, Export). `trailing` puts the page's actions and the profile button on the card and hides the title row.
export function HeroBand({
  period,
  tools,
  trailing,
  variant = "default",
  label,
  className,
  children,
}: {
  period?: ReactNode;
  tools?: ReactNode;
  trailing?: ReactNode;
  variant?: "default" | "eq";
  label?: string;
  className?: string;
  children?: ReactNode;
}) {
  const slots = useContext(HeroSlotsContext);
  const hideHead = slots?.hideHead;
  const replacesHead = trailing !== undefined;
  useEffect(() => {
    if (!replacesHead || !hideHead) return;
    hideHead(true);
    return () => hideHead(false);
  }, [replacesHead, hideHead]);
  const band = (
    <section
      aria-label={label}
      className={cn("band", variant === "eq" && "eq", className)}
    >
      {period && <div className="dbar">{period}</div>}
      {variant === "eq" ? <div className="eqn">{children}</div> : children}
      {tools && <div className="btools">{tools}</div>}
      {replacesHead && (
        <div className="bacts">
          {trailing}
          {slots?.profile}
        </div>
      )}
    </section>
  );
  return slots?.band ? createPortal(band, slots.band) : band;
}

// The headline figure: label over a big number, money with a small KES ahead of it.
export function BandFigure({
  label,
  value,
  currency = true,
  negative = false,
  main = false,
}: {
  label: ReactNode;
  value: ReactNode;
  currency?: boolean;
  negative?: boolean;
  // The first term of the petty cash sum.
  main?: boolean;
}) {
  return (
    <div className={cn(main && "t main")}>
      <div className="lab">{label}</div>
      <div className={cn("big", negative && "neg")}>
        {currency && <small>KES</small>}
        {currency && " "}
        {value}
      </div>
    </div>
  );
}

// The smaller figures beside the headline one.
export function BandStats({
  items,
}: {
  items: { label: ReactNode; value: ReactNode; tone?: "in" | "out" | "neg" }[];
}) {
  return (
    <div className="side">
      {items.map((item, index) => (
        <div key={index} className={item.tone}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

// A term and an operator of the petty cash sum (HeroBand variant "eq").
export function BandTerm({
  label,
  value,
}: {
  label: ReactNode;
  value: ReactNode;
}) {
  return (
    <div className="t">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function BandOp({ children }: { children: ReactNode }) {
  return (
    <span className="op" aria-hidden="true">
      {children}
    </span>
  );
}

// Inputs and selects on the headline card: glass on the brand colour.
export const bandControl =
  "min-w-0 rounded-[10px] border border-glass-line bg-glass px-[11px] py-2 font-semibold text-white placeholder:text-on-deep [&>option]:bg-surface [&>option]:text-ink";

// The bar above a list (.bar): toggles, filters, search, then Export and bulk actions. Align to the top when it holds
// a labelled field whose error may appear below it.
export function Toolbar({
  align = "center",
  className,
  ...props
}: ComponentProps<"div"> & { align?: "center" | "start" }) {
  return (
    <div
      {...props}
      className={cn(
        "flex flex-wrap gap-2",
        align === "start" ? "items-start" : "items-center",
        className,
      )}
    />
  );
}

// Pushes what follows to the end of a toolbar or action row.
export function Spacer() {
  return <span className="flex-1" aria-hidden="true" />;
}

export function Hint({ className, ...props }: ComponentProps<"p">) {
  return (
    <p {...props} className={cn("m-0 text-[13px] text-grey", className)} />
  );
}

// A stack of form cards (.form). Forms use the full width of the page, as in the design since v1.6.
export function FormLayout({ className, ...props }: ComponentProps<"div">) {
  return (
    <div {...props} className={cn("mt-5 flex flex-col gap-4", className)} />
  );
}

export function FormActions({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      {...props}
      className={cn("flex flex-wrap items-center gap-3", className)}
    />
  );
}

// Form columns at least 260px wide, as many as fit, that stack on narrow screens (.grid2). The fields share the
// row between them; `narrow` keeps each field to one column instead of stretching one or two across the page.
export function Grid2({
  narrow = false,
  className,
  ...props
}: ComponentProps<"div"> & { narrow?: boolean }) {
  return (
    <div
      {...props}
      className={cn(
        "grid gap-x-5 gap-y-3.5 max-[720px]:grid-cols-1",
        narrow
          ? "grid-cols-[repeat(auto-fill,minmax(260px,1fr))]"
          : "grid-cols-[repeat(auto-fit,minmax(260px,1fr))]",
        className,
      )}
    />
  );
}

// A heading inside a card or dialog (.access-group).
export function SubHeading({ className, ...props }: ComponentProps<"h3">) {
  return (
    <h3 {...props} className={cn("mt-4 mb-1 text-sm font-bold", className)} />
  );
}
