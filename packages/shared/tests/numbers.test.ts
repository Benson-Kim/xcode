import { describe, expect, it } from "vitest";

import {
  createFormatter,
  type FormatsInput,
  MAX_PERCENT_SHOWN,
  percentText,
  plural,
} from "@xcode/shared/format";

describe("amounts", () => {
  it.each<[FormatsInput, number, string]>([
    [{ numberDecimals: 0 }, 1500.5, "KES 1,501"],
    [{ numberDecimals: 0 }, 12345.678, "KES 12,346"],
    [{ numberDecimals: 3 }, 1.5, "KES 1.500"],
    [{ numberDecimals: 3 }, 1234.5678, "KES 1,234.568"],
    [{ numberDecimals: 3 }, 1234, "KES 1,234"],
    [{ useGrouping: false }, 1234567.5, "KES 1234567.50"],
    [{ useGrouping: false }, 1234567, "KES 1234567"],
    [{ locale: "en-IN" }, 1234567.5, "KES 12,34,567.50"],
    [{ locale: "de-DE" }, 1234567.891, "KES 1.234.567,89"],
    [{ currency: "USD" }, 5, "USD 5"],
    [{}, 0, "KES 0"],
    [{}, 1e12, "KES 1,000,000,000,000"],
    [{}, 0.005, "KES 0.01"],
  ])("with %o shows %d as %s", (settings, amount, expected) => {
    expect(createFormatter(settings).kes(amount)).toBe(expected);
  });

  it.each([
    [0, "KES 0"],
    [1500.5, "KES 1,500.50"],
    [-1500.5, "KES 1,500.50 loss"],
  ])("shows money %d as %s", (amount, expected) => {
    expect(createFormatter().money(amount)).toBe(expected);
  });
});

it("reports the currency and date pattern it formats with", () => {
  const formatter = createFormatter({ currency: "USD", datePattern: "short" });
  expect(formatter.currencyCode()).toBe("USD");
  expect(formatter.datePattern()).toBe("short");
  expect(createFormatter().datePattern()).toBe("medium");
});

describe("first day of the week", () => {
  it.each<[number | undefined, number]>([
    [0, 0],
    [1, 1],
    [3, 3],
    [6, 6],
    [7, 1],
    [-1, 1],
    [1.5, 1],
    [NaN, 1],
    [undefined, 1],
  ])("setting %s starts weeks on day %d", (setting, expected) => {
    expect(createFormatter({ firstDayOfWeek: setting }).firstDayOfWeek()).toBe(
      expected,
    );
  });

  it("starts on Monday without settings", () => {
    expect(createFormatter(null).firstDayOfWeek()).toBe(1);
    expect(createFormatter().firstDayOfWeek()).toBe(1);
  });
});

describe("percentages", () => {
  it.each([
    [0, "0%"],
    [83, "83%"],
    [83.4, "83.4%"],
    [115, "115%"],
    [-5, "-5%"],
    [MAX_PERCENT_SHOWN, "999%"],
    [999.5, "999%+"],
    [1000, "999%+"],
    [1249977794, "999%+"],
    // The most the API sends (it clamps to a 32-bit integer).
    [2147483647, "999%+"],
    [Infinity, "999%+"],
  ])("shows %d as %s", (percent, expected) => {
    expect(percentText(percent)).toBe(expected);
    expect(createFormatter().percentText(percent)).toBe(expected);
  });
});

describe("counts", () => {
  it.each([
    [1, "1 car"],
    [0, "0 cars"],
    [2, "2 cars"],
    [-1, "-1 cars"],
  ])("counts %d as %s", (count, expected) => {
    expect(plural(count, "car", "cars")).toBe(expected);
  });
});
