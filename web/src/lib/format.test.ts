import { expect, it } from "vitest";

import { date, shortId } from "./format";

it.each([
  ["9c5d7314-80b0-46cc-a772-889c215ab263", "9c5d7314"],
  ["9C5D7314-80B0-46CC-A772-889C215AB263", "9C5D7314"],
  ["retail_revenue", "retail_revenue"],
  ["source/main/orders", "source/main/orders"],
  ["9c5d7314-not-a-uuid", "9c5d7314-not-a-uuid"],
  ["0123456789abcdef0123456789abcdef", "0123456789abcdef0123456789abcdef"],
])("shortens only complete UUID identities: %s", (value, expected) => {
  expect(shortId(value)).toBe(expected);
});

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
