import type { components } from "../api/generated";

type Field = components["schemas"]["TemplateAttribute"];

function field(partial: Partial<Field> & Pick<Field, "key" | "type">): Field {
  return {
    name_zh: partial.key,
    name_en: partial.key,
    target: "object",
    required: false,
    default: null,
    options: [],
    minimum: null,
    maximum: null,
    max_length: 200,
    ...partial,
  };
}

/** One field of each of the five template attribute types. */
export const attributeFieldsFixture: Field[] = [
  field({
    key: "occluded",
    type: "boolean",
    name_zh: "被遮挡",
    name_en: "Occluded",
    default: false,
  }),
  field({
    key: "color",
    type: "enum",
    name_zh: "颜色",
    name_en: "Colour",
    required: true,
    options: [
      { value: "red", name_zh: "红", name_en: "Red" },
      { value: "blue", name_zh: "蓝", name_en: "Blue" },
    ],
  }),
  field({
    key: "tags",
    type: "multi_enum",
    name_zh: "标记",
    name_en: "Tags",
    options: [
      { value: "dirty", name_zh: "脏", name_en: "Dirty" },
      { value: "wet", name_zh: "湿", name_en: "Wet" },
    ],
  }),
  field({
    key: "count",
    type: "number",
    name_zh: "数量",
    name_en: "Count",
    minimum: 0,
    maximum: 9,
  }),
  field({ key: "note", type: "text", name_zh: "备注", name_en: "Note" }),
];

export const recordFieldFixture: Field = field({
  key: "scene",
  type: "enum",
  target: "record",
  name_zh: "场景",
  name_en: "Scene",
  required: true,
  options: [{ value: "day", name_zh: "白天", name_en: "Day" }],
});
