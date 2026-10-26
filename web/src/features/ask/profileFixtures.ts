import { unavailableAnswer } from "./testFixtures";

import type { AskAnswer } from "../../api/ask";

export const sensorAnswer: AskAnswer = {
  ...unavailableAnswer,
  id: "profile-answer",
  answer_kind: "profile",
  question: "Which device has most temperature gaps?",
  status: "answered",
  candidates: [],
  message:
    "Recorded sampling-axis gaps; these are not temperature-only missing values.",
  profile: {
    intent: "device_gaps",
    scope: "sampling_time_axis",
    sort_by: "gap_count",
    requested_column: "temperature",
    dataset: {
      dataset_id: "sensors",
      dataset_name: "First sensors",
      version_id: "processed",
    },
    candidates: [],
    ranking: [
      {
        device: "beta",
        interval_count: 1,
        total_gap_ms: 3000,
        evidence: [
          {
            dataset_id: "sensors",
            version_id: "processed",
            file_id: "derived",
            filename: "sensors.csv",
            source_file_id: "original",
            source_version_id: "import",
            row_coordinates: "original_source",
            time_column: "timestamp",
            device: "beta",
            rows: [7, 3],
            start_ms: 1700000000000,
            end_ms: 1700000004000,
            expected_interval_ms: 1000,
            gap_ms: 3000,
          },
        ],
      },
    ],
  },
};

export const ambiguousSensorAnswer: AskAnswer = {
  ...sensorAnswer,
  status: "clarification",
  message: "Choose the dataset before ranking devices.",
  profile: {
    intent: "device_gaps",
    scope: "sampling_time_axis",
    sort_by: "gap_count",
    requested_column: "temperature",
    ranking: [],
    reason_code: "ambiguous_dataset",
    candidates: [
      {
        dataset_id: "sensors",
        dataset_name: "First sensors",
        version_id: "processed",
      },
      {
        dataset_id: "other-sensors",
        dataset_name: "Second sensors",
        version_id: "processed-other",
      },
    ],
  },
};
