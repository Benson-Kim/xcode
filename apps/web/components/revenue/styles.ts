import type { StatusTone } from "@xcode/shared/revenue";

export const TONE_CLASS: Record<StatusTone, string> = {
  muted: "text-grey",
  normal: "",
  alert: "text-red",
};

export const HEAD =
  "border-b border-card-line bg-paper px-2 py-2.5 text-xs font-semibold whitespace-nowrap text-grey";
export const CELL =
  "border-b border-divider px-2 py-1.5 text-[15px] tabular-nums";
// Below 720px the seven day columns give way to each vehicle's week detail, which lists the same days.
export const DAY_COLUMN = "max-[720px]:hidden";
export const PILL =
  "rounded-full bg-divider px-2 py-0.5 text-xs font-bold whitespace-nowrap text-navy";
export const MINI_HEAD =
  "border-b border-card-line px-2 py-2 text-left text-xs font-semibold text-grey";
export const MINI =
  "border-b border-card-line/70 px-2 py-1.5 text-sm tabular-nums";
