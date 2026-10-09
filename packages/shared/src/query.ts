// "path?a=1&b=x,y": skips empty values and joins lists with commas.
export function withQuery(path: string, query: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    const text = Array.isArray(value) ? value.join(",") : value;
    if (text !== undefined && text !== null && text !== "")
      params.set(key, String(text));
  }
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}
