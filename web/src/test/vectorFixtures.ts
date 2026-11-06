import { evidenceRef, mention } from "./evidenceFixtures";

import type { Assertion, VectorQueryResult } from "../api/types";

export const referenceRef = { ...evidenceRef, asset_id: "reference-1" };
export const vectorGap: Assertion = {
  ...mention,
  id: "gap-1",
  predicate: "coverage_gap",
  object: referenceRef,
  anchors: [evidenceRef, referenceRef].map((asset_ref) => ({
    asset_ref,
    content_revision: "a".repeat(64),
    selector: { type: "whole" },
    schema_version: "1.0",
  })),
  measurement: {
    type: "coverage",
    similarity: 0.2,
    threshold: 0.8,
    nearest: referenceRef,
    reference_digest: "b".repeat(64),
    references: [
      {
        subject: referenceRef,
        revision: "1",
        state_revision: 0,
        content_revision: "a".repeat(64),
      },
    ],
  },
};
export const vectorResult: VectorQueryResult = {
  run_id: "run-1",
  kind: "coverage",
  snapshot: "c".repeat(64),
  reference_digest: "b".repeat(64),
  status: "current",
  items: [vectorGap],
  total: 2,
  next_cursor: "signed-page-2",
  report: {
    mode: "fake",
    status: "partial_success",
    nodes: [
      {
        mode: "fake",
        fake_version: "we-e2-fake-v1",
        real_quality: "not_tested",
        status: "partial_success",
        counts: { input: 3, eligible: 2, failed: 1, truncated: 0 },
        fake_requests: 2,
        fake_usage: 10,
        fake_cost_nanos: 50,
        cache_hits: 0,
      },
    ],
    attempts: [
      {
        id: "attempt-1",
        state: "UNKNOWN",
        usage: null,
        token_bound: 10,
        reserved_nanos: 50,
      },
    ],
  },
  events: [
    {
      event_id: "event-1",
      operator: "evidence.coverage_gap",
      mode: "fake",
      implementation: "we-e2-fake-v1",
      contract: "we-e1-v1",
      inputs: [evidenceRef, referenceRef],
    },
  ],
};
