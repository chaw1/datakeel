import { cedar, relation, sourceRef } from "../../test/kgFixtures";

import { unavailableAnswer } from "./testFixtures";

import type {
  AskAnswer,
  KnowledgeAnswer,
  KnowledgeClaim,
  KnowledgeSubject,
} from "../../api/ask";

export const shipmentSubject: KnowledgeSubject = {
  asset_ref: {
    ...sourceRef,
    asset_type: "metric",
    asset_id: "shipment_revenue",
  },
  name: "出货额",
  kind: "metric",
};
export const ownerClaim: KnowledgeClaim = {
  assertion_id: "claim-owner",
  head: { ...cedar, name: "周岩", type: "person" },
  predicate: "owns",
  tail: { ...cedar, name: "出货额", type: "metric" },
  relation_status: "candidate",
  verification: "verified",
  evidence: [
    {
      source: sourceRef,
      document: "handoff.txt",
      text: "周岩负责出货额。",
      start: 0,
      end: 8,
    },
  ],
  subject_link: {
    entity: cedar,
    asset_ref: shipmentSubject.asset_ref,
    assertion_id: "link-subject",
    link_status: "candidate",
  },
  other_end: { status: "not_applicable", entity: cedar },
  consistency: null,
};
export const ownerKnowledge: KnowledgeAnswer = {
  intent: "owner",
  intent_candidates: [],
  subject: shipmentSubject,
  system_records: [
    {
      asset_ref: {
        ...sourceRef,
        asset_type: "owner",
        asset_id: "supply-owner",
      },
      name: "供应链负责人",
      relation: "owner",
    },
  ],
  system_message: "",
  claims: [ownerClaim],
  pending_ambiguous_links: 1,
};
export const knowledgeAnswer: AskAnswer = {
  ...unavailableAnswer,
  id: "knowledge-answer",
  answer_kind: "knowledge",
  question: "出货额谁负责？",
  status: "answered",
  message: "System records and document claims are shown separately.",
  candidates: [],
  knowledge: ownerKnowledge,
  subject_candidates: [],
};
export const claimExplanation = {
  relation: {
    ...relation,
    head: ownerClaim.head,
    tail: ownerClaim.tail,
    assertion: {
      ...relation.assertion,
      id: ownerClaim.assertion_id,
      predicate: "kg.owns",
    },
  },
  extractor: "replay",
  sources: [
    {
      asset_ref: sourceRef,
      filename: "handoff.txt",
      text: ownerClaim.evidence[0].text,
    },
  ],
};
