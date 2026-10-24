export const statusLabels = {
  candidate: "kgCandidate",
  accepted: "kgAccepted",
  rejected: "kgRejected",
  verified: "kgVerified",
  needs_review: "kgNeedsReview",
  queued: "kgQueued",
  running: "kgRunning",
  completed: "kgCompleted",
  partial: "kgPartial",
  budget_exceeded: "kgBudgetExceeded",
  failed: "kgFailed",
} as const;
export const issueLabels = {
  evidence: "kgMissingEvidence",
  head: "kgMissingHead",
  tail: "kgMissingTail",
  endpoint_undeclared: "kgUndeclared",
} as const;
export const proposalLabels = {
  unknown_relation: "kgUnknownRelation",
  domain_range: "kgDomainRange",
  endpoint_ambiguous: "kgEndpointAmbiguous",
  unknown_entity_type: "kgUnknownEntityType",
} as const;
