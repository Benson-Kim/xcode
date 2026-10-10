import type { StatusTone } from "@xcode/shared/revenue";

export const TONE_CLASS: Record<StatusTone, string> = {
  muted: "muted",
  normal: "",
  alert: "text-clay",
};

// Below 720px the seven day columns give way to each vehicle's week detail, which lists the same days.
export const DAY_COLUMN = "max-[720px]:hidden";
