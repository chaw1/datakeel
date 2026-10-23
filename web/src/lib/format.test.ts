import { expect, it } from "vitest";

import { date } from "./format";

it("keeps the same compact local calendar format in both interface languages", () => {
  const timestamp = "2026-10-22T12:00:00Z";
  expect(date(timestamp, "en")).toMatch(/^10-22 \d{2}:00$/);
  expect(date(timestamp, "zh")).toBe(date(timestamp, "en"));
  expect(date(undefined)).toBe("—");
  expect(date("invalid")).toBe("invalid");
});

it.each(["en", "zh"] as const)(
  "keeps an explicit UTC reference instant independent of local time in %s",
  (locale) => {
    expect(date("2026-10-01T00:00:00Z", locale, "UTC")).toBe("10-01 00:00");
    expect(date("2026-10-01T08:00:00+08:00", locale, "UTC")).toBe(
      "10-01 00:00",
    );
    expect(date("2026-10-01T00:00:00Z", locale, "Asia/Shanghai")).toBe(
      "10-01 08:00",
    );
  },
);
