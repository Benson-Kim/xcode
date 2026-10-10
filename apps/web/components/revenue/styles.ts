import type { StatusTone } from "@xcode/shared/revenue";

export const TONE_CLASS: Record<StatusTone, string> = {
  muted: "text-slate",
  normal: "",
  alert: "text-clay",
};

export const HEAD =
  "border-b border-line px-2 py-2.5 text-[11.5px] font-bold tracking-[.08em] whitespace-nowrap text-slate uppercase";
export const CELL =
  "border-b border-divider px-2 py-1.5 text-[15px] tabular-nums";
export const EDGE = "first:pl-(--gut) last:pr-(--gut)";
// Below 720px the seven day columns give way to each vehicle's week detail, which lists the same days.
export const DAY_COLUMN = "max-[720px]:hidden";
export const PILL =
  "rounded-full bg-paper-2 px-2.5 py-0.5 text-xs font-bold whitespace-nowrap text-ink-2";
export const MINI_HEAD =
  "border-b border-line px-2 py-2 text-left text-[11.5px] font-bold tracking-[.08em] text-slate uppercase";
export const MINI =
  "border-b border-card-line/70 px-2 py-1.5 text-sm tabular-nums";
