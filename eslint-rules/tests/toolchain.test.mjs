import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);
const read = (file) => readFileSync(path.join(root, file), "utf8");
const json = (file) => JSON.parse(read(file));

const rootManifest = json("package.json");
const workspaces = Object.fromEntries(
  rootManifest.workspaces.map((dir) => [dir, json(`${dir}/package.json`)]),
);
const lock = json("package-lock.json").packages;
const dependencies = (manifest) => ({
  ...manifest.dependencies,
  ...manifest.devDependencies,
  ...manifest.peerDependencies,
});
const version = (text) => text.split(".").map(Number);
const compare = (a, b) => {
  const [x, y] = [version(a), version(b)];
  for (let i = 0; i < 3; i++)
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) - (y[i] ?? 0);
  return 0;
};
// Enough of semver for the ">=a.b.c <x.y.z" ranges peers use here.
const satisfies = (actual, range) =>
  range.split(/\s+/).every((part) => {
    const [, op, bound] =
      /^(>=|<=|>|<|=)?(\d+(?:\.\d+){0,2})$/.exec(part) ??
      assert.fail(`unsupported range ${range}`);
    const order = compare(actual, bound);
    return (
      { ">=": order >= 0, "<=": order <= 0, ">": order > 0, "<": order < 0 }[
        op
      ] ?? order === 0
    );
  });

describe("toolchain", () => {
  // typescript-eslint parses every workspace with one TypeScript, so tsc must check the same version everywhere.
  it("uses one TypeScript range in every workspace and at the root", () => {
    const range = rootManifest.devDependencies.typescript;
    assert.ok(range, "the root declares typescript");
    for (const [dir, manifest] of Object.entries(workspaces))
      assert.equal(
        dependencies(manifest).typescript,
        range,
        `${dir} declares typescript ${range}`,
      );
    const copies = Object.keys(lock).filter((key) =>
      key.endsWith("node_modules/typescript"),
    );
    assert.deepEqual(
      copies,
      ["node_modules/typescript"],
      "the lock holds a single TypeScript",
    );
  });

  it("installs a TypeScript that typescript-eslint supports", () => {
    const installed = lock["node_modules/typescript"].version;
    for (const [key, entry] of Object.entries(lock))
      if (
        /node_modules\/(typescript-eslint|@typescript-eslint\/[^/]+)$/.test(
          key,
        ) &&
        entry.peerDependencies?.typescript
      )
        assert.ok(
          satisfies(installed, entry.peerDependencies.typescript),
          `${key} supports typescript ${installed}`,
        );
  });

  it("declares every package the lint config imports", () => {
    const imported = [
      ...read("eslint.config.mjs").matchAll(
        /^import .* from "([^."][^"]*)";?\r?$/gm,
      ),
    ].map(([, name]) =>
      name.startsWith("@")
        ? name.split("/").slice(0, 2).join("/")
        : name.split("/")[0],
    );
    assert.ok(imported.length > 0);
    for (const name of imported)
      assert.ok(
        dependencies(rootManifest)[name],
        `the root package.json declares ${name}`,
      );
  });

  it("keeps frameworks out of the shared package", () => {
    const names = Object.keys(dependencies(workspaces["packages/shared"]));
    assert.deepEqual(
      names.filter((name) =>
        /^(react|react-dom|react-native|next|expo)(-|$)|^@(react-native|expo|next)\//.test(
          name,
        ),
      ),
      [],
    );
  });

  // React Native pins the phone's React; the web app runs a newer one. metro.config.cjs and jest.config.cjs route the
  // phone's react imports to its own copy, so each app must pin react and react-dom exactly and together.
  it("pins each app's React exactly, with react-dom in step", () => {
    for (const dir of ["apps/web", "apps/mobile"]) {
      const { react, "react-dom": dom } = workspaces[dir].dependencies;
      assert.match(react, /^\d+\.\d+\.\d+$/, `${dir} pins react exactly`);
      assert.equal(dom, react, `${dir} pins react-dom to react`);
    }
    const phone = workspaces["apps/mobile"].dependencies.react;
    if (phone !== workspaces["apps/web"].dependencies.react)
      assert.equal(
        lock["apps/mobile/node_modules/react"]?.version,
        phone,
        "the phone keeps its own React copy",
      );
  });

  it("lints the web app for the React version it runs", () => {
    const [, linted] =
      /react: \{ version: "(\d+\.\d+)" \}/.exec(read("eslint.config.mjs")) ??
      assert.fail("no react version setting");
    assert.ok(
      workspaces["apps/web"].dependencies.react.startsWith(`${linted}.`),
    );
  });
});
