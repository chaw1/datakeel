import { version } from "../../test/fixtures";

import type { TrainingEvaluation, TrainingRun } from "../../api/llmData";

export const trainingRun: TrainingRun = {
  id: "training-run-1",
  dataset_id: "dataset-1",
  version_id: version.id,
  created_at: "2026-10-29T00:00:00Z",
  cleaned_version_id: null,
  ledger_sha256: "c".repeat(64),
  report: {
    rule_version: "1.0",
    config: {
      format: "auto",
      max_tokens: 8192,
      near_distance: 8,
      near_similarity: 0.9,
      repetition_threshold: 0.45,
      contamination_ngram: 13,
      contamination_threshold: 0.2,
      refusal_phrases: [],
      sample_limit: 50,
      max_line_bytes: 1048576,
    },
    pii_records: 1,
    records: 4,
    valid_records: 3,
    issue_counts: {
      invalid_json: 1,
      pii_email: 1,
      near_duplicate: 1,
      contamination: 1,
    },
    languages: { en: 2, zh: 1, mixed: 1 },
    formats: { messages: 3, auto: 1 },
    files: [
      {
        file_id: "file-1",
        filename: "training.jsonl",
        records: 4,
        valid_records: 3,
        issue_counts: { invalid_json: 1 },
      },
    ],
    samples: [
      {
        id: "record-1",
        file_id: "file-1",
        line: 2,
        content_hash: "b".repeat(64),
        format: "messages",
        language: "en",
        language_confidence: 0.98,
        estimated_tokens: 30,
        preview: "Please contact [EMAIL] for the generated sample.",
        issues: [
          {
            code: "pii_email",
            field: "text",
            message: "Detected email",
            evidence: "[EMAIL]",
            start: 15,
            end: 33,
            related_id: null,
          },
        ],
        decision: "redact",
        reasons: ["pii_email"],
      },
    ],
    duplicate_clusters: [["record-1", "record-3"]],
    contamination_hits: [
      {
        code: "contamination",
        field: "prompt",
        message: "User-registered evaluation entry matched",
        evidence: "reference n-gram coverage=0.800; n=13",
        start: null,
        end: null,
        related_id: "evaluation-1:7",
      },
    ],
    chosen_longer_ratio: 0.5,
    preference_records: 2,
    dropped: 2,
    redacted: 1,
    kept: 1,
    ledger_sha256: "c".repeat(64),
    source_sha256: { "file-1": "a".repeat(64) },
    evaluation_sha256: {},
    dedup_backend: "python",
  },
};

export const evaluation: TrainingEvaluation = {
  id: "evaluation-1",
  dataset_id: "dataset-1",
  name: "Generated review questions",
  source_dataset_id: "dataset-1",
  version_id: version.id,
  file_ids: ["evaluation-file"],
  created_at: "2026-10-29T00:00:00Z",
};
