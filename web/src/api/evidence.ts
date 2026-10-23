import { get, post } from "./client";

import type {
  ActionRun,
  DecideAssertionsParams,
  EvidenceQuery,
  EvidenceQueryResult,
  EvidenceSample,
} from "./types";

export function queryEvidence(query: EvidenceQuery) {
  return post<EvidenceQueryResult>("/api/evidence/query", query);
}
export function evidencePath(assetId: string, versionId: string) {
  return `/api/evidence/assets/${encodeURIComponent(assetId)}?version_id=${encodeURIComponent(versionId)}`;
}
export function getEvidence(assetId: string, versionId: string) {
  return get<EvidenceSample>(evidencePath(assetId, versionId));
}
export function decideAssertion(
  assertionId: string,
  status: DecideAssertionsParams["status"],
  reason: string,
) {
  return post<ActionRun>("/api/evidence/assertions/decide", {
    assertion_ids: [assertionId],
    status,
    reason,
  } satisfies DecideAssertionsParams);
}
