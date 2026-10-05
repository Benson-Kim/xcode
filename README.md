# Multi-platform authentication application

.NET 10 API, Next.js web, and React Native mobile monorepo. Bootstrap in progress; runnable setup and authentication policy will be documented here.

## Web server settings

- `API_URL`: where the web proxy reaches the API (default `http://localhost:5000`).
- `TRUSTED_PROXY_HOPS`: how many trusted reverse proxies sit in front of the web server (a non-negative integer, default `0`). The sign-in rate limit is per client, and Next.js keeps any `X-Forwarded-For` a client sends, so the proxy only names the client from the entry the outermost trusted proxy appended: the Nth from the right. At `0` no client address is forwarded and the API sees one shared address for the web server (safe, but one limit for everyone). `X-Real-IP` and `Forwarded` are never used. The API believes the forwarded address only from `ForwardedHeaders:KnownProxies` (loopback when unset).
