import { cn } from "./cn";

// The design's figure cards (.hero): money out tinted red, cash received green, the closing balance blue.
const TONES = {
  plain: "border-card-line bg-surface",
  out: "border-red-line/70 bg-red-bg/45",
  in: "border-green-line/70 bg-green-bg/45",
  close: "border-blue/25 bg-blue-tint",
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
        "flex flex-col gap-1.5 rounded-2xl border px-5 py-4.5 shadow-[0_1px_2px_rgb(20_33_61/4%)]",
        TONES[tone],
      )}
    >
      <small className="text-[13px] text-grey">{label}</small>
      <strong
        className={cn(
          "text-[26px] leading-[1.15] font-bold tabular-nums",
          bad && "text-red",
        )}
      >
        {value}
      </strong>
    </div>
  );
}
