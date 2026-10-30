import { fieldName } from "./editors/attributes";

import type { AttributeProblem } from "./editors/attributes";
import type { Translate } from "../../i18n/context";

const SHAPES = {
  box: "wbProblemBox",
  polygon: "wbProblemPolygon",
  span: "wbProblemSpan",
} as const;

/** Name the field and the annotation that needs it, e.g. "Box 2: Occluded is required". */
export function problemText(
  problem: AttributeProblem,
  t: Translate,
  locale: string,
) {
  const where =
    problem.shape === "record"
      ? t("wbProblemRecord")
      : t(SHAPES[problem.shape], { index: problem.index });
  return t(
    problem.kind === "required" ? "wbAttributeMissing" : "wbAttributeInvalid",
    { where, field: fieldName(problem.field, locale) },
  );
}
