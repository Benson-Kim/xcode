module.exports = {
  preset: "jest-expo",
  testMatch: ["**/tests/**/*.test.ts", "**/tests/**/*.test.tsx"],
  setupFilesAfterEnv: ["<rootDir>/tests/setup.ts"],
  clearMocks: true,
  // A cold first render lazily transforms React Native modules in CI.
  testTimeout: 15000,
  moduleNameMapper: {
    "^react$": require.resolve("react"),
    "^react/(.*)$": "<rootDir>/node_modules/react/$1",
  },
};
