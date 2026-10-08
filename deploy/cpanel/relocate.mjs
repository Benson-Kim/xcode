// Makes a Next.js standalone build independent of the folder it was built in: the build's absolute root becomes
// a path relative to server.js in server.js, and "." in required-server-files.json.
// Usage: node relocate.mjs <build root> <standalone dir>
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const [root, standalone] = process.argv.slice(2);
if (!root || !standalone) {
  console.error("Usage: node relocate.mjs <build root> <standalone dir>");
  process.exit(2);
}
const web = path.join(standalone, "apps", "web");
const under = (value) =>
  value === root ||
  value.startsWith(`${root}/`) ||
  value.startsWith(`${root}\\`);

for (const file of [
  path.join(web, "server.js"),
  path.join(web, ".next", "required-server-files.json"),
]) {
  const script = file.endsWith(".js");
  let changed = 0;
  const text = readFileSync(file, "utf8").replace(
    /"((?:[^"\\]|\\.)*)"/g,
    (literal) => {
      let value;
      try {
        value = JSON.parse(literal);
      } catch {
        return literal;
      }
      if (typeof value !== "string") return literal;
      if (under(value)) {
        changed++;
        const rest = value.slice(root.length).replace(/\\/g, "/");
        if (!script) return JSON.stringify(`.${rest}`);
        return `require("path").join(__dirname, "../..")${rest ? ` + ${JSON.stringify(rest)}` : ""}`;
      }
      // A build on Windows also writes some relative paths with backslashes.
      if (value.startsWith(".next\\") || value === "apps\\web") {
        changed++;
        return JSON.stringify(value.replace(/\\/g, "/"));
      }
      return literal;
    },
  );
  if (text.includes(root) || text.includes(JSON.stringify(root).slice(1, -1)))
    throw new Error(`${file} still names ${root}`);
  writeFileSync(file, text);
  console.log(`${path.relative(standalone, file)}: ${changed} paths`);
}
