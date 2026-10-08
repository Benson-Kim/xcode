import { afterEach, expect, it, vi } from "vitest";

import { formatDateOnly } from "@xcode/shared/dates";
import { remember } from "../src/intlCache";
import {
  createFormatter,
  currentFormats,
  formatPhone,
  normalisePhone,
  phoneError,
} from "@xcode/shared/format";

it("formats dates and compact ranges using the shared medium pattern", () => {
  const { formatDate, formatDateRange } = createFormatter();
  expect(formatDate(new Date("2026-09-28T00:00:00Z"))).toBe("28 Sep 2026");
  expect(formatDateRange("2026-09-21", "2026-09-27")).toBe("21 to 27 Sep 2026");
  expect(formatDateRange("2026-09-28", "2026-10-04")).toBe(
    "28 Sep to 4 Oct 2026",
  );
  expect(formatDateRange("2025-12-29", "2026-01-04")).toBe(
    "29 Dec 2025 to 4 Jan 2026",
  );
});

it("formats date ranges without compaction in locale-specific patterns", () => {
  const { formatDateRange } = createFormatter({
    locale: "en-GB",
    datePattern: "short",
  });
  expect(formatDateRange("2026-09-28", "2026-10-04")).toBe(
    "28/09/2026 to 04/10/2026",
  );
});

it("formats timestamps in the configured time zone and clock style", () => {
  const nairobi = createFormatter({ timeZone: "Africa/Nairobi" });
  expect(nairobi.formatDateTime("2026-09-20T13:05:00Z")).toBe(
    "20 Sep 2026 16:05",
  );
  const utc = createFormatter({ timeZone: "UTC", hour12: true });
  expect(utc.formatDateTime("2026-09-20T13:05:00Z")).toBe(
    "20 Sep 2026 1:05 pm",
  );
});

it("normalises Kenyan phone numbers without hiding excess digits", () => {
  expect(normalisePhone("+254 711 000 001")).toBe("0711000001");
  expect(normalisePhone("711-000-001")).toBe("0711000001");
  expect(normalisePhone("0711 000 0012")).toBe("07110000012");
  expect(formatPhone("0711 000 0012")).toBe("0711 000 0012");
  expect(phoneError("0711000001")).toBe("");
  expect(phoneError("07110000012")).toBe(
    "Enter all 10 numbers, starting 07 or 01.",
  );
});

it("keeps formatter instances independent of each other and of the default", () => {
  const nairobi = createFormatter({ timeZone: "Africa/Nairobi" });
  const london = createFormatter({
    currency: "GBP",
    timeZone: "UTC",
    hour12: true,
    firstDayOfWeek: 0,
  });
  expect(nairobi.kes(1500.5)).toBe("KES 1,500.50");
  expect(london.kes(1500.5)).toBe("GBP 1,500.50");
  expect(nairobi.formatDateTime("2026-09-20T13:05:00Z")).toBe(
    "20 Sep 2026 16:05",
  );
  expect(london.formatDateTime("2026-09-20T13:05:00Z")).toBe(
    "20 Sep 2026 1:05 pm",
  );
  expect(nairobi.firstDayOfWeek()).toBe(1);
  expect(london.firstDayOfWeek()).toBe(0);
  expect(london.money(-10)).toBe("GBP 10 loss");
  expect(createFormatter().kes(10)).toBe("KES 10");
});

afterEach(() => vi.restoreAllMocks());

it("builds a small constant number of Intl instances however many values it formats", () => {
  const dateTimeFormat = vi.spyOn(Intl, "DateTimeFormat");
  const numberFormat = vi.spyOn(Intl, "NumberFormat");
  const formatter = createFormatter({
    locale: "en-KE",
    timeZone: "Africa/Mombasa",
  });
  const short = createFormatter({
    locale: "en-KE",
    timeZone: "Africa/Mombasa",
    datePattern: "short",
  });
  const base = Date.parse("2026-09-20T13:05:00Z");
  for (let i = 0; i < 1000; i++) {
    const stamp = new Date(base + i * 3_600_000).toISOString();
    formatter.formatDateTime(stamp);
    short.formatDateTime(stamp);
    formatter.formatDateOnly("2026-09-05");
    formatter.kes(i % 2 ? i : i + 0.5);
  }
  expect(dateTimeFormat.mock.calls.length).toBeLessThanOrEqual(6);
  expect(numberFormat.mock.calls.length).toBeLessThanOrEqual(2);
});

it("falls back to the host time zone for an invalid zone, every time", () => {
  const dateTimeFormat = vi.spyOn(Intl, "DateTimeFormat");
  const broken = createFormatter({ timeZone: "Mars/Olympus" });
  const host = createFormatter({ timeZone: undefined as unknown as string });
  const first = broken.formatDateTime("2026-09-20T13:05:00Z");
  expect(first).toBe(host.formatDateTime("2026-09-20T13:05:00Z"));
  const afterFirst = dateTimeFormat.mock.calls.length;
  for (let i = 0; i < 50; i++) {
    expect(broken.formatDateTime("2026-09-20T13:05:00Z")).toBe(first);
  }
  expect(dateTimeFormat.mock.calls.length).toBe(afterFirst);
});

it("never shares output between formatters with different options", () => {
  const grouped = createFormatter({ numberDecimals: 2, useGrouping: true });
  const plain = createFormatter({ numberDecimals: 0, useGrouping: false });
  const german = createFormatter({ locale: "de-DE" });
  expect(grouped.kes(12345.5)).toBe("KES 12,345.50");
  expect(plain.kes(12345.5)).toBe("KES 12346");
  expect(german.kes(12345.5)).toBe("KES 12.345,50");
  expect(grouped.kes(12345.5)).toBe("KES 12,345.50");
  expect(grouped.kes(12345)).toBe("KES 12,345");
  const long = createFormatter({ datePattern: "long", timeZone: "UTC" });
  const short = createFormatter({ datePattern: "short", timeZone: "UTC" });
  expect(long.formatDate(new Date("2026-09-05T00:00:00Z"))).not.toBe(
    short.formatDate(new Date("2026-09-05T00:00:00Z")),
  );
});

it("matches toLocaleString for amounts and still rejects an invalid locale tag", () => {
  const formatter = createFormatter({ locale: "en-GB", numberDecimals: 2 });
  for (const amount of [0, 5, 0.1, 1234.567, -9876543.21, 1e9, 99.999]) {
    const expected = amount.toLocaleString("en-GB", {
      minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
      maximumFractionDigits: 2,
      useGrouping: true,
    });
    expect(formatter.kes(amount)).toBe(`KES ${expected}`);
  }
  const bad = createFormatter({ locale: "not a locale" });
  expect(() => bad.kes(1)).toThrow(RangeError);
  expect(() => bad.kes(1)).toThrow(RangeError);
});

it("shows a date-only value as its own calendar day in every time zone", () => {
  const zones = [
    "America/New_York",
    "Pacific/Honolulu",
    "UTC",
    "Africa/Nairobi",
    "Pacific/Kiritimati",
  ];
  for (const timeZone of zones) {
    const medium = createFormatter({ timeZone });
    expect(medium.formatDateOnly("2026-09-05")).toBe("5 Sep 2026");
    expect(medium.formatDateRange("2026-09-21", "2026-09-27")).toBe(
      "21 to 27 Sep 2026",
    );
    const long = createFormatter({
      timeZone,
      datePattern: "long",
      locale: "en-GB",
    });
    expect(long.formatDateOnly("2026-09-05")).toBe("5 September 2026");
    const short = createFormatter({
      timeZone,
      datePattern: "short",
      locale: "en-GB",
    });
    expect(short.formatDateOnly("2026-09-05")).toBe("05/09/2026");
  }
  expect(
    formatDateOnly("2026-01-01", {
      locale: "en-GB",
      timeZone: "America/New_York",
      datePattern: "medium",
      hour12: false,
    }),
  ).toBe("1 Jan 2026");
});

it("still shows a timestamp on the organization's local day", () => {
  const newYork = createFormatter({ timeZone: "America/New_York" });
  expect(newYork.formatDateTime("2026-09-05T02:30:00Z")).toBe(
    "4 Sep 2026 22:30",
  );
});

it("clears a cache that grows past its bound and keeps serving values", () => {
  const cache = new Map<number, number>();
  for (let i = 0; i < 450; i++)
    expect(remember(cache, i, () => i * 2)).toBe(i * 2);
  expect(cache.size).toBeLessThanOrEqual(200);
  expect(remember(cache, 449, () => -1)).toBe(898);
});

it("formats a number as kes does, without the currency", () => {
  const settings = [
    {},
    { useGrouping: false },
    { locale: "de-DE" },
    { numberDecimals: 0 },
    { currency: "USD" },
  ];
  for (const next of settings) {
    const formatter = createFormatter(next);
    for (const amount of [0, 1, 1250, 1250.5, -5, 1234567.891]) {
      expect(formatter.formatNumber(amount)).toBe(
        formatter.kes(amount).slice(formatter.currencyCode().length + 1),
      );
    }
  }
  expect(createFormatter().formatNumber(1250)).toBe("1,250");
  expect(createFormatter().formatNumber(1250.5)).toBe("1,250.50");
});

it("puts the weekday before a date in the organization's pattern", () => {
  const medium = createFormatter({ datePattern: "medium", locale: "en-GB" });
  const short = createFormatter({ datePattern: "short", locale: "en-GB" });
  const long = createFormatter({ datePattern: "long", locale: "en-GB" });
  expect(medium.formatWeekdayDate("2026-09-29")).toBe("Tue 29 Sep 2026");
  expect(short.formatWeekdayDate("2026-09-29")).toBe("Tue 29/09/2026");
  expect(long.formatWeekdayDate("2026-09-29")).toBe("Tue 29 September 2026");
});

it.each([
  [1200, 1000, "KES 200 above"],
  [850, 1000, "KES 150 below"],
  [1000, 1000, "On target"],
  [0.1 + 0.2, 0.3, "On target"],
  [1000.5, 1000, "KES 0.50 above"],
])("says %s against %s expected as '%s'", (actual, expected, text) => {
  expect(createFormatter().formatDifference(actual, expected)).toBe(text);
});

it.each([
  ["the current name", { useGrouping: false, numberDecimals: 0 }, "KES 12346"],
  ["the old name", { useGroupping: false, numberDecimals: 0 }, "KES 12346"],
  [
    "both names, the current one wins",
    { useGrouping: true, useGroupping: false },
    "KES 12,345.50",
  ],
  ["an explicit undefined", { useGrouping: undefined }, "KES 12,345.50"],
  ["neither name", {}, "KES 12,345.50"],
])("groups digits for %s", (_name, settings, expected) => {
  expect(createFormatter(settings).kes(12345.5)).toBe(expected);
});

it("never exposes the old spelling of digit grouping", () => {
  const { formats } = createFormatter({ useGroupping: false });
  expect(formats.useGrouping).toBe(false);
  expect("useGroupping" in formats).toBe(false);
});

it("renames digit grouping only when the current name is absent", () => {
  expect(currentFormats({ useGroupping: false })).toEqual({
    useGrouping: false,
  });
  expect(currentFormats({ useGrouping: true, useGroupping: false })).toEqual({
    useGrouping: true,
  });
  expect(currentFormats({ currency: "USD" })).toEqual({ currency: "USD" });
});
