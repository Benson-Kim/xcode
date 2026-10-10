import { cn } from "./cn";

// A labelled figure in the design's summary strip (.msum span + b). Cash received is teal, a negative clay.
const TONES = {
  plain: "",
  out: "",
  in: "text-teal",
  close: "",
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
    <div className="msum">
      <div>
        <span>{label}</span>
        <b className={cn(bad ? "text-clay" : TONES[tone])}>{value}</b>
      </div>
    </div>
  );
}
