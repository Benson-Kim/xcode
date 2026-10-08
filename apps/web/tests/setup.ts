import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { clearDataCache } from "../lib/data";

afterEach(() => {
  cleanup();
  clearDataCache();
});
