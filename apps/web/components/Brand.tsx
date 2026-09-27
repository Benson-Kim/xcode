import { BrandIcon, cn } from "./ui";

// The XCODE mark and name. `compact` hides the "Fleet finance" line on narrow screens (top bar).
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span aria-hidden="true" className="grid size-9.5 shrink-0 place-items-center rounded-[10px] bg-navy text-white">
        <BrandIcon />
      </span>
      <span>
        <span className="block text-lg font-bold tracking-[0.04em]">XCODE</span>
        <span className={cn("block text-[13px] text-grey", compact && "max-[899px]:hidden")}>Fleet finance</span>
      </span>
    </span>
  );
}
