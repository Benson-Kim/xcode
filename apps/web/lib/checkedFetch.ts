// A bot check in front of the host can answer any URL, including our /api routes, with a 200 HTML page. The app's
// own routes never return HTML, so that answer means the request was intercepted and nothing reached the server.
export class SecurityCheckError extends Error {
  constructor() {
    super("A security check interrupted this request, so nothing was sent. Reload the page and try again.");
    this.name = "SecurityCheckError";
  }
}

// fetch for the browser's calls to /api/*. Not retried and not a status: only a reload passes the check.
export async function checkedFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, init);
  if (response.ok && /^\s*text\/html/i.test(response.headers.get("Content-Type") ?? ""))
    throw new SecurityCheckError();
  return response;
}
