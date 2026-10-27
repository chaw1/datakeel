import type { DatasheetDocument } from "../../api/datasheets";

export const sheet: DatasheetDocument = {
  id: "sheet-1",
  dataset_id: "dataset-1",
  version_id: "version-1",
  language: "en",
  mode: "template",
  created_at: "2026-10-27T00:00:00Z",
  published: false,
  stale: false,
  facts: [
    {
      id: "fact-name",
      chapter: "composition",
      source_type: "dataset",
      source_id: "dataset-1",
      field: "name",
      value: "Sample collection",
      recorded_at: "2026-10-27T00:00:00Z",
    },
  ],
  sections: [
    { key: "motivation", title: "Motivation", sentences: [], missing: true },
    {
      key: "composition",
      title: "Composition",
      sentences: [
        { text: "The dataset is Sample collection.", fact_ids: ["fact-name"] },
      ],
      missing: false,
    },
    { key: "collection", title: "Collection", sentences: [], missing: true },
    {
      key: "preprocessing",
      title: "Preprocessing",
      sentences: [],
      missing: true,
    },
    { key: "uses", title: "Uses", sentences: [], missing: true },
    {
      key: "distribution",
      title: "Distribution",
      sentences: [],
      missing: true,
    },
    { key: "maintenance", title: "Maintenance", sentences: [], missing: true },
  ],
  dropped_sentences: [
    {
      text: "Acme supplied 900 files.",
      fact_ids: ["fact-name"],
      reasons: ["unsupported_number", "unsupported_term"],
    },
  ],
};
