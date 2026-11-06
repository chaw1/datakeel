import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { translator } from "../../i18n/context";
import { evidenceEn } from "../../i18n/evidenceEn";
import { evidenceZh } from "../../i18n/evidenceZh";
import { vectorGap } from "../../test/vectorFixtures";

import { VectorMeasurement } from "./VectorMeasurement";

it("keeps vector controls and states available in both languages", () => {
  expect(
    Object.keys(evidenceEn).filter((key) => key.startsWith("vec")),
  ).toEqual(Object.keys(evidenceZh).filter((key) => key.startsWith("vec")));
  expect(translator("zh")("vecTitle")).toBe("向量证据");
  expect(translator("en")("vecTitle")).toBe("Vector evidence");
  expect(translator("zh")("vecState_stale")).toContain("失效");
});
it("renders direct duplicate similarity and threshold without substituting distance", () => {
  render(
    <VectorMeasurement
      assertion={{
        ...vectorGap,
        predicate: "semantic_duplicate_of",
        measurement: {
          type: "cosine_duplicate",
          similarity: 0.9,
          threshold: 0.8,
        },
      }}
    />,
  );
  expect(screen.getByText("0.9")).toBeVisible();
  expect(screen.getByText("0.8")).toBeVisible();
});
