import { BrandIcon, Skeleton, cn } from "./ui";

// The organization's mark and name: its uploaded logo, or the XCODE mark in its brand colour.
// `compact` hides the second line on narrow screens (top bar).
export function Brand({
  name = "XCODE",
  subline = "Fleet finance",
  logo,
  logoAlt,
  loading = false,
  compact = false,
}: {
  name?: string;
  subline?: string;
  logo?: string | null;
  logoAlt?: string;
  loading?: boolean;
  compact?: boolean;
}) {
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      {logo ? (
        // The logo is a data URL from the API, which next/image cannot optimise.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logo}
          alt={logoAlt || name}
          className="size-9.5 shrink-0 rounded-[10px] object-contain"
        />
      ) : (
        <span
          aria-hidden="true"
          className="grid size-9.5 shrink-0 place-items-center rounded-[10px] bg-brand text-white"
        >
          <BrandIcon />
        </span>
      )}
      {loading ? (
        <span className="flex w-28 flex-col gap-1.5" aria-hidden="true">
          <Skeleton className="h-4 w-20" />
          <Skeleton
            className={cn("h-3 w-24", compact && "max-[899px]:hidden")}
          />
        </span>
      ) : (
        <span className="min-w-0">
          <span className="block truncate text-lg font-bold tracking-[0.04em]">
            {name}
          </span>
          <span
            className={cn(
              "block truncate text-[13px] text-grey",
              compact && "max-[899px]:hidden",
            )}
          >
            {subline}
          </span>
        </span>
      )}
    </span>
  );
}
