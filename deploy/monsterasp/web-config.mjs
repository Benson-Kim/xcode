// Writes the IIS web.config for the API on MonsterASP, with its settings as environment variables taken from this
// process's environment. The file holds secrets: write it to a temporary place and delete it after the upload.
// Usage: node web-config.mjs <file>
import { writeFileSync } from "node:fs";

const required = [
  "ConnectionStrings__Auth",
  "Auth__SigningKey",
  "Email__Host",
  "Email__From",
  "Cors__Origins__0",
];
const optional = [
  "Email__Port",
  "Email__Username",
  "Email__Password",
  "Email__EnableSsl",
];
const missing = required.filter((key) => !process.env[key]);
if (missing.length) {
  console.error(`Missing settings: ${missing.join(", ")}`);
  process.exit(1);
}
const xml = (value) =>
  String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
const variables = [
  ["ASPNETCORE_ENVIRONMENT", "Production"],
  ...[...required, ...optional]
    .filter((key) => process.env[key])
    .map((key) => [key, process.env[key]]),
]
  .map(
    ([key, value]) =>
      `          <environmentVariable name="${key}" value="${xml(value)}" />`,
  )
  .join("\n");

writeFileSync(
  process.argv[2],
  `<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <location path="." inheritInChildApplications="false">
    <system.webServer>
      <handlers>
        <add name="aspNetCore" path="*" verb="*" modules="AspNetCoreModuleV2" resourceType="Unspecified" />
      </handlers>
      <aspNetCore processPath="dotnet" arguments=".\\Auth.Api.dll" stdoutLogEnabled="true" stdoutLogFile=".\\logs\\stdout" hostingModel="inprocess">
        <environmentVariables>
${variables}
        </environmentVariables>
      </aspNetCore>
    </system.webServer>
  </location>
</configuration>
`,
);
