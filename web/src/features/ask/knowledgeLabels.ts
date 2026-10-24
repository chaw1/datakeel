export const knowledgeKindLabels = {
  metric: "knowledgeMetric",
  table: "knowledgeTable",
  view: "knowledgeView",
  owner: "knowledgeRole",
  kg_entity: "knowledgeEntity",
} as const;

export const knowledgeIntentLabels = {
  owner: "knowledgeIntentOwner",
  upstream: "knowledgeIntentUpstream",
  downstream: "knowledgeIntentDownstream",
  owned: "knowledgeIntentOwned",
  related: "knowledgeRelated",
} as const;

export const knowledgeFocusLabels = {
  person: "knowledgeFocusPerson",
  table: "knowledgeFocusTable",
  metric: "knowledgeFocusMetric",
  location: "knowledgeFocusLocation",
  list: "knowledgeFocusList",
  unknown: "knowledgeFocusUnknown",
} as const;
