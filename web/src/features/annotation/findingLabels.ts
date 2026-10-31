import type { AnnotationReport } from "../../api/annotation";
import type { MessageKey } from "../../i18n/en";

export type FindingCode =
  AnnotationReport["result"]["findings"][number]["code"];

/** Translated names of the P26 suspicion rules, shared by the findings table and AI pre-review. */
export const findingLabels: Record<FindingCode, MessageKey> = {
  minority_label: "annotationMinority",
  near_duplicate_conflict: "annotationDuplicate",
  bbox_size_outlier: "annotationBoxSize",
  bbox_aspect_outlier: "annotationBoxAspect",
  invalid_bbox: "annotationInvalidBox",
  multilabel_conflict: "annotationMultilabel",
  invalid_span: "annotationInvalidSpan",
  bbox_category_minority: "annotationBoxCategory",
  bbox_missing: "annotationBoxMissing",
  bbox_extra: "annotationBoxExtra",
  duplicate_bbox: "annotationBoxDuplicate",
  span_category_minority: "annotationSpanCategory",
  span_boundary_minority: "annotationSpanBoundary",
  span_missing: "annotationSpanMissing",
  span_extra: "annotationSpanExtra",
  duplicate_span: "annotationSpanDuplicate",
  span_length_outlier: "annotationSpanLength",
  rare_category: "annotationRareCategory",
};
