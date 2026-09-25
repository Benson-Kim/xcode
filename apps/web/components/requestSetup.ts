export async function requestSetup<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/setup/${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  const body = await response.json();
  if (!response.ok) throw new Error(body.title || body.detail || "Could not load setup data.");
  return body as T;
}
