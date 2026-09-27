const { getDefaultConfig } = require("expo/metro-config");
const path = require("node:path");
const config = getDefaultConfig(__dirname);
// The app's renderers need its exact React (and, for the browser preview, React DOM) version, not the
// newer copies the web workspace hoists to the repository root.
const pinned = /^react(-dom)?(\/|$)/;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (pinned.test(moduleName)) {
    return context.resolveRequest({ ...context, originModulePath: path.join(__dirname, "package.json") }, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};
module.exports = config;
