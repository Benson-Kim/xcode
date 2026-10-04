import { expect, it } from "vitest";
import { MAX_PERCENT_SHOWN, percentText } from "../lib/format";

it("shows a share of a target as it is, up to 999%", () => {
  expect(percentText(0)).toBe("0%");
  expect(percentText(83)).toBe("83%");
  expect(percentText(115)).toBe("115%");
  expect(percentText(MAX_PERCENT_SHOWN)).toBe("999%");
});

it("reads 999%+ for anything above the cap, however large", () => {
  expect(percentText(1000)).toBe("999%+");
  expect(percentText(1249977794)).toBe("999%+");
  // The most the API sends (it clamps to a 32-bit integer).
  expect(percentText(2147483647)).toBe("999%+");
});
