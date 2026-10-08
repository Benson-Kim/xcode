// cPanel (Passenger) startup file: runs the Next.js web server. The API runs on its own host, named in
// app/release.json, which the staging deploy writes. An API process an earlier version started on this account is
// stopped, so it no longer counts against the account's process limit.
"use strict";
const fs = require("fs");
const path = require("path");

const root = __dirname;
const logs = path.join(root, "logs");
fs.mkdirSync(logs, { recursive: true });
const startLog = fs.createWriteStream(path.join(logs, "start.log"), {
  flags: "a",
});
const log = (...parts) =>
  startLog.write(
    `${new Date().toISOString()} [${process.pid}] ${parts.join(" ")}\n`,
  );

function stopOldApis() {
  let entries = [];
  try {
    entries = fs.readdirSync("/proc");
  } catch {
    return;
  }
  for (const entry of entries) {
    if (!/^\d+$/.test(entry)) continue;
    try {
      const command = fs
        .readFileSync(`/proc/${entry}/cmdline`, "utf8")
        .split("\0")[0];
      if (!command.endsWith("/xcode-web/api/Auth.Api")) continue;
      process.kill(Number(entry), "SIGTERM");
      log(`stopped old API process ${entry}`);
    } catch {}
  }
}

const release = JSON.parse(
  fs.readFileSync(path.join(root, "app", "release.json"), "utf8"),
);
process.env.API_URL = release.apiUrl;
process.env.NODE_ENV = "production";
if (process.platform !== "win32") stopOldApis();
log(
  `node ${process.version} starting web ${release.commit} against ${release.apiUrl}`,
);
require(path.join(root, "app", "apps", "web", "server.js"));

// update.sh also touches tmp/restart.txt; should Passenger miss it, a new build still takes over within a minute:
// this process exits and Passenger starts the new one on the next request.
setInterval(() => {
  let current = release.commit;
  try {
    current = JSON.parse(
      fs.readFileSync(path.join(root, "app", "release.json"), "utf8"),
    ).commit;
  } catch {}
  if (current === release.commit) return;
  log(`build ${current} installed; restarting`);
  process.exit(0);
}, 60_000).unref();
