const { getDefaultConfig } = require("expo/metro-config");
const path = require("node:path");
const config = getDefaultConfig(__dirname);
// Native's renderer needs its exact React version, not the separately patched web React.
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === "react" || moduleName.startsWith("react/")) {
    return context.resolveRequest({ ...context, originModulePath: path.join(__dirname, "package.json") }, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};
module.exports = config;
