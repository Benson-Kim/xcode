// Runs once as the server starts, before it takes a request: a production server with a missing setting stops here.
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (process.env.NEXT_PHASE === "phase-production-build") return;
  const { trustedProxyHops } = await import("./app/api/body");
  trustedProxyHops();
}
