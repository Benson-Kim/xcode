import { useState } from "react";

import type { Period } from "@xcode/shared/periods";
import type { ReportExportFormat } from "@xcode/shared/reports";

import { useFormats } from "../../lib/formats";
import { fetchWithSession } from "../../lib/session";
import { failureMessage } from "../pettycash/request";

// A file name the browsers and file systems accept.
export const safeFileName = (name: string) =>
  name
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, " ")
    .trim();

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

// Fetches a report's file through the proxy and offers it as a download. The proxy forwards only the content type,
// so the file is named here.
export async function downloadReport(path: string, fileName: string) {
  let response: Response;
  try {
    response = await fetchWithSession(`/api/${path}`);
  } catch (error) {
    if (error instanceof TypeError)
      throw new Error("Unable to reach the server. Check your connection.");
    throw error;
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      body.detail ||
        (response.status === 403
          ? "Your access does not include this. Ask your admin if you need it."
          : "The export could not be created."),
    );
  }
  saveBlob(await response.blob(), safeFileName(fileName));
}

// Export for the Reports page: one download at a time, and the reason when one fails. The file is named after the
// report and, for a dated one, its period.
export function useReportExport() {
  const formats = useFormats();
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  async function run(
    path: string,
    label: string,
    period: Period | null,
    format: ReportExportFormat,
  ) {
    setExporting(true);
    setError("");
    const named = !period
      ? ""
      : period.from === period.to
        ? formats.formatDateOnly(period.from)
        : formats.formatDateRange(period.from, period.to).replace(" to ", "-");
    try {
      await downloadReport(
        path,
        `${label}${named ? ` ${named}` : ""}.${format}`,
      );
    } catch (reason) {
      setError(failureMessage(reason));
    } finally {
      setExporting(false);
    }
  }

  return { exporting, error, run };
}
