import { describe, expect, it } from "vitest";

import { translator } from "../../i18n/context";

import { countProblem } from "./templateContent";

import type { AnnotationRecord, ProductionTemplate } from "./editors/types";

const t = translator("en");

function template(
  annotationType: "segment" | "box",
  minimum: number,
  maximum: number,
): ProductionTemplate {
  return {
    id: annotationType,
    name: annotationType,
    annotation_type: annotationType,
    component_config: {
      components: [annotationType, "classification"],
    },
    validation_rules: {
      ...(minimum ? { min_annotations: minimum } : {}),
      max_annotations: maximum,
    },
    attributes: [],
    revision: 1,
    archived: false,
  };
}

function annotation(segments: number, labels: number): AnnotationRecord {
  return {
    sample_id: "audio",
    annotator_id: "ann",
    labels: Array.from(
      { length: labels },
      (_, index) => `label-${String(index)}`,
    ),
    segments: Array.from({ length: segments }, (_, index) => ({
      category: "speech",
      start_ms: index,
      end_ms: index + 1,
    })),
    media_duration_ms: 1000,
  };
}

describe("segment annotation counts", () => {
  it("allows one segment plus one label at max one", () => {
    expect(countProblem(annotation(1, 1), template("segment", 1, 1), t)).toBe(
      "",
    );
  });

  it("does not let a label fill the second required segment", () => {
    expect(countProblem(annotation(1, 1), template("segment", 2, 5), t)).toBe(
      "Needs at least 2 annotations (now 1)",
    );
  });

  it("counts zero and multiple segments exactly with multiple labels", () => {
    expect(
      countProblem(annotation(0, 3), template("segment", 1, 2), t),
    ).toContain("at least");
    expect(countProblem(annotation(2, 3), template("segment", 1, 2), t)).toBe(
      "",
    );
    expect(
      countProblem(annotation(3, 3), template("segment", 1, 2), t),
    ).toContain("at most");
  });

  it("keeps the legacy sum rule for other mixed templates", () => {
    const record: AnnotationRecord = {
      sample_id: "image",
      annotator_id: "ann",
      labels: ["a"],
      boxes: [{ category: "a", x1: 0, y1: 0, x2: 1, y2: 1 }],
    };
    expect(countProblem(record, template("box", 0, 1), t)).toContain("at most");
  });
});
