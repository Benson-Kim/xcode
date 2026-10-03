import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";

// Page title and subtitle (.page-title / .page-sub).
export function PageHeader({ title, description }: { title: ReactNode; description?: ReactNode }) {
  return (
    <header>
      <h1 className="m-0 text-[28px] leading-[1.2] font-bold">{title}</h1>
      {description && <p className="mt-1 mb-0 text-grey">{description}</p>}
    </header>
  );
}

// The white bar above a list holding filters, counts and the add action (.toolbar). Align to the top when it
// holds a labelled field whose error may appear below it.
export function Toolbar({ align = "center", className, ...props }: ComponentProps<"div"> & { align?: "center" | "start" }) {
  return (
    <div
      {...props}
      className={cn(
        "mt-5 flex flex-wrap gap-3 rounded-[14px] border border-card-line bg-white p-3",
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
  return <p {...props} className={cn("m-0 text-[13px] text-grey", className)} />;
}

// A stack of form cards (.form). Forms use the full width of the page, as in the design since v1.6.
export function FormLayout({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("mt-5 flex flex-col gap-4", className)} />;
}

export function FormActions({ className, ...props }: ComponentProps<"div">) {
  return <div {...props} className={cn("flex flex-wrap items-center gap-3", className)} />;
}

// Form columns at least 260px wide, as many as fit, that stack on narrow screens (.grid2). The fields share the
// row between them; `narrow` keeps each field to one column instead of stretching one or two across the page.
export function Grid2({ narrow = false, className, ...props }: ComponentProps<"div"> & { narrow?: boolean }) {
  return (
    <div
      {...props}
      className={cn(
        "grid gap-x-5 gap-y-3.5 max-[720px]:grid-cols-1",
        narrow ? "grid-cols-[repeat(auto-fill,minmax(260px,1fr))]" : "grid-cols-[repeat(auto-fit,minmax(260px,1fr))]",
        className,
      )}
    />
  );
}

// A heading inside a card or dialog (.access-group).
export function SubHeading({ className, ...props }: ComponentProps<"h3">) {
  return <h3 {...props} className={cn("mt-4 mb-1 text-sm font-bold", className)} />;
}
