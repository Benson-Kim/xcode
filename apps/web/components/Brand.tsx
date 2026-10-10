import { Skeleton, cn } from "./ui";

// The organization's mark and name on the brand colour: its uploaded logo, or the XCODE mark, then the wordmark.
// `compact` hides the second line on narrow screens.
export function Brand({
  name = "XCODE",
  subline = "Fleet finance",
  logo,
  logoAlt,
  loading = false,
  compact = false,
  size = 30,
}: {
  name?: string;
  subline?: string;
  logo?: string | null;
  logoAlt?: string;
  loading?: boolean;
  compact?: boolean;
  size?: number;
}) {
  return (
    <span className="logo">
      {logo ? (
        // The logo is a data URL from the API, which next/image cannot optimise.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logo}
          alt={logoAlt || name}
          width={size}
          height={size}
          className="mark shrink-0 rounded-[8px] object-contain"
        />
      ) : (
        <svg
          className="mark"
          width={size}
          height={size}
          viewBox="0 0 40 40"
          aria-hidden="true"
        >
          <path className="a" d="M9 9 L31 31" />
          <path className="b" d="M31 9 L24.5 15.5" />
          <path className="b" d="M15.5 24.5 L9 31" />
        </svg>
      )}
      {loading ? (
        <span className="txt flex w-28 flex-col gap-1.5" aria-hidden="true">
          <Skeleton className="h-4 w-20 opacity-40" />
          <Skeleton
            className={cn(
              "h-3 w-24 opacity-40",
              compact && "max-[899px]:hidden",
            )}
          />
        </span>
      ) : (
        <span className="txt">
          <span className="wm">{name}</span>
          <span className="wmsub">{subline}</span>
        </span>
      )}
    </span>
  );
}
