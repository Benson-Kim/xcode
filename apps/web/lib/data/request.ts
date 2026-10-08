import { fetchWithSession } from "../session";

// A refused request. The message is what to show; the status and body let a screen handle one refusal itself
// (for example a 409 that carries the record now saved).
export class ApiError extends Error {
  status: number;
  body: Record<string, unknown>;
  constructor(message: string, status: number, body: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

const NOT_PERMITTED =
  "Your access does not include this. Ask your admin if you need it.";

// Calls the app's API through its Next.js proxy routes: `path` is relative to /api, for example "setup/companies".
// An expired access token is refreshed once on the way.
export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetchWithSession(`/api/${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch (error) {
    if (error instanceof TypeError)
      throw new ApiError(
        "Unable to reach the server. Check your connection.",
        0,
        {},
      );
    throw error;
  }
  const body = await response.json().catch(() => ({}));
  // The API's detail says what to fix;
  // its title is only the category (for example "Invalid setup change"). A refusal with no detail is said in plain
  // words rather than as the category ("Not permitted in this organization or data scope.").
  if (!response.ok)
    throw new ApiError(
      body.detail ||
        (response.status === 403 ? NOT_PERMITTED : body.title) ||
        "The request could not be completed.",
      response.status,
      body,
    );
  return body as T;
}
