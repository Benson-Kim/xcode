"use client";

import { useState } from "react";

import type { RevenueWeek } from "@xcode/shared/revenue";

import { apiRequest } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { failureMessage } from "../pettycash/request";
import { saveBlob } from "../reports/exportReport";
import { useToast } from "../ui";
import { canvasBlob, drawSummaryImage } from "./drawSummaryImage";
import { summaryLayout, type SummaryLayout } from "./summaryImage";

export const SUMMARY_IMAGE_LOG_PATH = "setup/revenue/export/image";

// What the change log records about the picture: the week, the company filter and the search it was drawn with.
type ImageLog = {
  weekStart: string;
  companyId: string | null;
  q: string | null;
};

type Shown = {
  layout: SummaryLayout;
  log: ImageLog;
  canvas: HTMLCanvasElement | null;
};

// The Summary image export (Web v2.40 to v2.45): drawn on the device from the week on screen and shown in a pop up;
// Save writes the change-log row first, the way every export is logged, and only then hands over the PNG.
export function useSummaryImage(
  week: RevenueWeek | undefined,
  companyId: string,
  q: string,
) {
  const formats = useFormats();
  const toast = useToast();
  const [shown, setShown] = useState<Shown | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function open() {
    if (!week) return;
    const layout = summaryLayout(week, companyId, formats.formatNumber);
    setError("");
    setShown({
      layout,
      log: {
        weekStart: week.weekStart,
        companyId: companyId || null,
        q: q || null,
      },
      canvas: null,
    });
    try {
      const canvas = await drawSummaryImage(layout);
      setShown((current) =>
        current?.layout === layout ? { ...current, canvas } : current,
      );
    } catch (reason) {
      setError(failureMessage(reason));
    }
  }

  async function save() {
    if (!shown?.canvas || saving) return;
    setSaving(true);
    setError("");
    try {
      const blob = await canvasBlob(shown.canvas);
      await apiRequest(SUMMARY_IMAGE_LOG_PATH, {
        method: "POST",
        body: JSON.stringify(shown.log),
      });
      saveBlob(blob, shown.layout.fileName);
      setShown(null);
      toast(`Saved ${shown.layout.fileName}`);
    } catch (reason) {
      setError(failureMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  function close() {
    if (saving) return;
    setShown(null);
    setError("");
  }

  return { shown, saving, error, open, save, close };
}
