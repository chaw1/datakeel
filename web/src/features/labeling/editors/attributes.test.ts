import { describe, expect, it } from "vitest";

import {
  attributeFieldsFixture,
  recordFieldFixture,
} from "../../../test/attributeFixtures";
import { labelingProject } from "../../../test/labelingFixtures";

import {
  attributeFields,
  attributeProblems,
  fieldName,
  optionName,
  valueFits,
  withDefaults,
} from "./attributes";

import type { ProductionTemplate } from "./types";

const [boolean, enumField, multi, number, text] = attributeFieldsFixture;
const template: ProductionTemplate = {
  ...(labelingProject.template as ProductionTemplate),
  attributes: [...attributeFieldsFixture, recordFieldFixture],
};

describe("template attributes", () => {
  it("splits fields by target and names them per locale", () => {
    expect(attributeFields(template, "object")).toHaveLength(5);
    expect(attributeFields(template, "record")).toEqual([recordFieldFixture]);
    expect(fieldName(enumField, "zh")).toBe("颜色");
    expect(fieldName(enumField, "en")).toBe("Colour");
    expect(optionName(enumField, "blue", "zh")).toBe("蓝");
    expect(optionName(enumField, "green", "en")).toBe("green");
  });

  it("fills only absent defaults", () => {
    expect(withDefaults(undefined, [boolean])).toEqual({ occluded: false });
    expect(withDefaults({ occluded: true }, [boolean])).toEqual({
      occluded: true,
    });
  });

  it("applies the server's value rules", () => {
    expect(valueFits(boolean, "yes")).toBe(false);
    expect(valueFits(enumField, "green")).toBe(false);
    expect(valueFits(enumField, "red")).toBe(true);
    expect(valueFits(multi, ["wet", "wet"])).toBe(false);
    expect(valueFits(multi, ["wet", "dirty"])).toBe(true);
    expect(valueFits(number, 10)).toBe(false);
    expect(valueFits(number, -1)).toBe(false);
    expect(valueFits(number, 9)).toBe(true);
    expect(valueFits(text, "x".repeat(201))).toBe(false);
    expect(valueFits(text, "ok")).toBe(true);
  });

  it("names the field and the shape of each problem in display order", () => {
    const problems = attributeProblems(
      {
        sample_id: "s",
        annotator_id: "a",
        attributes: {},
        boxes: [
          { category: "cat", x1: 0, y1: 0, x2: 1, y2: 1, attributes: {} },
          {
            category: "cat",
            x1: 0,
            y1: 0,
            x2: 1,
            y2: 1,
            attributes: { color: "green", note: "  " },
          },
        ],
      },
      template,
    );
    expect(
      problems.map((item) => [
        item.shape,
        item.index,
        item.field.key,
        item.kind,
      ]),
    ).toEqual([
      ["record", 0, "scene", "required"],
      ["box", 1, "color", "required"],
      ["box", 2, "color", "invalid"],
    ]);
  });

  it("leaves templates without attribute fields unchanged", () => {
    expect(
      attributeProblems(
        { sample_id: "s", annotator_id: "a", attributes: { free: [1] } },
        { ...template, attributes: [] },
      ),
    ).toEqual([]);
  });
});
