import { cn } from "./cn";

// White figure tiles: the tone only colours the number (cash received teal, money out and negatives clay).
const TONES = {
  plain: "text-ink",
  out: "text-ink",
  in: "text-teal",
  close: "text-ink",
} as const;

export function Figure({
  label,
  value,
  tone,
  bad,
}: {
  label: string;
  value: string;
  tone: keyof typeof TONES;
  bad?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-[18px] border border-line bg-surface px-5 py-[18px]",
      )}
    >
      <small className="text-xs font-bold tracking-[.07em] text-slate uppercase">
        {label}
      </small>
      <strong
        className={cn(
          "text-[26px] leading-[1.15] font-extrabold tabular-nums",
          bad ? "text-clay" : TONES[tone],
        )}
      >
        {value}
      </strong>
    </div>
  );
}
