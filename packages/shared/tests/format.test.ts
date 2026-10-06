import { expect, it } from "vitest";

import {
  createFormatter,
  formatPhone,
  normalisePhone,
  phoneError,
} from "../src/format";

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
