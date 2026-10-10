import type { ReactNode } from "react";

import { cn } from "./cn";

// A vehicle registration, drawn as a plate (.reg).
export function RegPlate({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <strong
      className={cn(
        "inline-flex items-baseline gap-[7px] rounded-[7px] bg-paper-2 px-[9px] py-[3px] text-[13px] font-bold tracking-[.03em] whitespace-nowrap text-ink",
        className,
      )}
    >
      {children}
    </strong>
  );
}
