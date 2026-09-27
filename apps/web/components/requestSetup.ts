import { fetchWithSession } from "../lib/session";

export async function requestSetup<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithSession(`/api/setup/${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  // The API's detail says what to fix; its title is only the category ("Invalid setup change").
  if (!response.ok) throw new Error(body.detail || body.title || "Could not load setup data.");
  return body as T;
}
