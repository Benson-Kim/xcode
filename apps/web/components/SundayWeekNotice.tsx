"use client";

import { useState } from "react";

import {
  SUNDAY_WEEK_NOTICE_TITLE,
  sundayWeekNotice,
  sundayWeekNoticeDetail,
  type Appearance,
} from "@xcode/shared/appearance";

import { useFormats } from "../lib/formats";
import { Button } from "./ui";

// The change date this browser dismissed the notice for.
export const SUNDAY_WEEK_DISMISSED_KEY = "xcode.sunday-week-notice";

function dismissedDate() {
  try {
    return window.localStorage.getItem(SUNDAY_WEEK_DISMISSED_KEY);
  } catch {
    return null;
  }
}

// v2.41 go-live: tells everyone signed in that the week now runs Sunday to Saturday, for seven days from the date the
// server moved it, until dismissed on this browser.
export function SundayWeekNotice({
  appearance,
}: {
  appearance: Appearance | null;
}) {
  const { formatDateOnly } = useFormats();
  const [dismissed, setDismissed] = useState(dismissedDate);
  const since = sundayWeekNotice(appearance, dismissed);
  if (!since) return null;

  function dismiss() {
    try {
      window.localStorage.setItem(SUNDAY_WEEK_DISMISSED_KEY, since!);
    } catch {
      // A private window can refuse to store anything; the notice still goes for this visit.
    }
    setDismissed(since);
  }

  return (
    <div
      role="status"
      className="mb-4 flex flex-wrap items-center gap-3 rounded-lg bg-blue-soft px-4 py-3 text-navy"
    >
      <p className="min-w-[200px] flex-1">
        <strong>{SUNDAY_WEEK_NOTICE_TITLE}</strong>{" "}
        {sundayWeekNoticeDetail(formatDateOnly(since))}
      </p>
      <Button tone="outline" size="sm" onClick={dismiss}>
        Dismiss
      </Button>
    </div>
  );
}
