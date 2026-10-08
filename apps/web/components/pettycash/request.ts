import { apiRequest, ApiError } from "../../lib/data";

export function withQuery(
  path: string,
  params: Record<string, string | undefined>,
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value) query.set(key, value);
  const search = query.toString();
  return search ? `${path}?${search}` : path;
}

export const ENTRIES_PATH = "setup/pettycash/entries";

export const entryPath = (id: string, action?: string) =>
  `${ENTRIES_PATH}/${id}${action ? `/${action}` : ""}`;

export const optionsPath = (date: string) =>
  withQuery("setup/pettycash/options", { date });

export function sendJson<T>(
  method: "POST" | "PUT",
  path: string,
  body: unknown,
) {
  return apiRequest<T>(path, { method, body: JSON.stringify(body) });
}

export const isConflict = (error: unknown) =>
  error instanceof ApiError && error.status === 409;

// crypto.randomUUID exists only on https or localhost; a phone opening the app over plain http on the LAN lacks it.
export function newEntryId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export const failureMessage = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "The request could not be completed.";
