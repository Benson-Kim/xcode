import type { ReactNode } from "react";

import { cn } from "./cn";

// A vehicle registration, drawn as a plate (.reg). With an amount, the vehicle's share of a split sits inside it.
export function RegPlate({
  amount,
  className,
  children,
}: {
  amount?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span className={cn("reg", className)}>
      {children}
      {amount !== undefined && <i>{amount}</i>}
    </span>
  );
}

// Several plates together, as an expense split across vehicles (.splitv).
export function RegPlates({ children }: { children: ReactNode }) {
  return <div className="splitv">{children}</div>;
}
