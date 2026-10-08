import { describe, expect, it } from "vitest";

import { ordinal } from "@xcode/shared/dates";
import { createFormatter } from "@xcode/shared/format";

describe("ordinals", () => {
  it.each([
    [0, "0th"],
    [1, "1st"],
    [2, "2nd"],
    [3, "3rd"],
    [4, "4th"],
    [11, "11th"],
    [12, "12th"],
    [13, "13th"],
    [21, "21st"],
    [22, "22nd"],
    [23, "23rd"],
    [101, "101st"],
    [111, "111th"],
    [112, "112th"],
    [113, "113th"],
    [121, "121st"],
  ])("%d is %s", (value, expected) => {
    expect(ordinal(value)).toBe(expected);
  });
});

describe("times of day", () => {
  const instant = "2026-09-20T13:05:00Z";

  // The machine's own zone differs between developers and CI, so it is compared, never written down.
  it.each([["Not/AZone"], [""], [undefined]])(
    "falls back to the device's zone for %j",
    (timeZone) => {
      const device = createFormatter({ timeZone: undefined }).formatDateTime(
        instant,
      );
      expect(
        createFormatter({ timeZone: timeZone as string }).formatDateTime(
          instant,
        ),
      ).toBe(device);
      expect(
        createFormatter({ timeZone: "Pacific/Kiritimati" }).formatDateTime(
          instant,
        ),
      ).not.toBe(device);
    },
  );

  it.each([
    ["UTC", "20 Sep 2026 13:05"],
    ["Africa/Nairobi", "20 Sep 2026 16:05"],
    ["africa/nairobi", "20 Sep 2026 16:05"],
    ["Pacific/Kiritimati", "21 Sep 2026 03:05"],
  ])("shows the time in %s", (timeZone, expected) => {
    expect(createFormatter({ timeZone }).formatDateTime(instant)).toBe(
      expected,
    );
  });

  it.each([
    ["2026-09-20T00:05:00Z", true, "20 Sep 2026 12:05 am"],
    ["2026-09-20T12:00:00Z", true, "20 Sep 2026 12:00 pm"],
    ["2026-09-20T23:59:00Z", true, "20 Sep 2026 11:59 pm"],
    ["2026-09-20T00:05:00Z", false, "20 Sep 2026 00:05"],
  ])("shows %s with hour12 %s as %s", (value, hour12, expected) => {
    expect(
      createFormatter({ timeZone: "UTC", hour12 }).formatDateTime(value),
    ).toBe(expected);
  });

  it.each([
    [undefined, "28 Sep 2026"],
    ["Africa/Nairobi", "29 Sep 2026"],
    ["America/New_York", "28 Sep 2026"],
  ])("dates an instant in %s", (timeZone, expected) => {
    expect(
      createFormatter().formatDate(new Date("2026-09-28T22:00:00Z"), timeZone),
    ).toBe(expected);
  });
});
