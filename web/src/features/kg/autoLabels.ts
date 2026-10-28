import type { MessageKey } from "../../i18n/en";

export const autoReasonLabels = {
  low_confidence: "kgAutoLowConfidence",
  structure_diagram: "kgAutoStructureDiagram",
  struck_or_greyed_rows: "kgAutoStruckOrGreyedRows",
  sparse_text: "kgAutoSparseText",
  ocr_failed: "kgAutoOCRFailed",
  clean_text: "kgAutoCleanText",
} as const satisfies Record<string, MessageKey>;
