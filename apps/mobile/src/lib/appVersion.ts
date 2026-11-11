import appConfig from "../../app.json";

// The version people see, and the one every request names so the API can refuse a version older than it supports.
export const appVersion = appConfig.expo.version;
export const androidPackage = appConfig.expo.android.package;
