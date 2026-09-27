import { fetchWithSession } from "../session";

// Calls the app's API through its Next.js proxy routes: `path` is relative to /api, for example "setup/companies".
// An expired access token is refreshed once on the way.
export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetchWithSession(`/api/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  // The API's detail says what to fix;
  // its title is only the category (for example "Invalid setup change").
  if (!response.ok)
    throw new Error(
      body.detail || body.title || "The request could not be completed.",
    );
  return body as T;
}
