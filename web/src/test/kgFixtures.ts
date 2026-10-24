import { actionPlan } from "./actionFixtures";
import { mention } from "./evidenceFixtures";
import { dataset } from "./fixtures";

import type {
  KGEntity,
  KGExplanation,
  KGGraph,
  KGProfile,
  KGRelation,
  KGResult,
  KGRun,
  KGSchema,
} from "../api/kg";
import type { ActionPlan, Assertion } from "../api/types";

export const kgDataset = { ...dataset, metadata: { kg_samples: true } };
export const sourceRef = {
  asset_id: "notes-1",
  asset_type: "file",
  namespace: "default",
  version: "version-1",
};
export const sourceText = "🚀 cafe\u0301 Cedar develops Reed. Cedar.";
export function kgAnchor(
  start: number,
  end: number,
): Assertion["anchors"][number] {
  return {
    ...mention.anchors[0],
    asset_ref: sourceRef,
    content_revision: "a".repeat(64),
    schema_version: "1.0",
    selector: { type: "text_span", start, end },
  };
}
export const cedar: KGEntity = {
  asset_ref: { ...sourceRef, asset_type: "kg_entity", asset_id: "cedar" },
  name: "Cedar",
  type: "Organization",
  mention_count: 2,
  mentions: [{ ...mention, anchors: [kgAnchor(7, 12), kgAnchor(28, 33)] }],
};
export const reed: KGEntity = {
  ...cedar,
  asset_ref: { ...cedar.asset_ref, asset_id: "reed" },
  name: "Reed",
  type: "Product",
  mention_count: 1,
  mentions: [{ ...mention, anchors: [kgAnchor(22, 26)] }],
};
export const relation: KGRelation = {
  head: cedar,
  tail: reed,
  extractor: "replay",
  model: "recorded-model",
  extraction_id: "kg-run-1",
  assertion: {
    ...mention,
    id: "relation-good",
    subject: cedar.asset_ref,
    object: reed.asset_ref,
    predicate: "kg.develops",
    verification: "verified",
    anchors: [kgAnchor(7, 27), kgAnchor(7, 12), kgAnchor(22, 26)],
    verification_detail: {
      evidence: { type: "text_span", start: 7, end: 27 },
      head: { type: "text_span", start: 7, end: 12 },
      tail: { type: "text_span", start: 22, end: 26 },
      issues: [],
      locations: [],
    },
  },
};
export const suspect: KGRelation = {
  ...relation,
  head: {
    ...cedar,
    name: "Vapor",
    asset_ref: { ...cedar.asset_ref, asset_id: "vapor" },
  },
  assertion: {
    ...relation.assertion,
    id: "relation-review",
    verification: "needs_review",
    verification_detail: {
      evidence: { type: "text_span", start: 7, end: 27 },
      head: null,
      tail: { type: "text_span", start: 22, end: 26 },
      issues: [{ code: "head", role: "head" }],
      locations: [],
    },
  },
};
export const kgResult: KGResult = {
  dataset_id: dataset.id,
  version_id: "version-1",
  entities: [cedar, reed],
  relations: [relation, suspect],
  truncated: false,
};
export const explanation: KGExplanation = {
  relation: suspect,
  sources: [{ asset_ref: sourceRef, filename: "notes.txt", text: sourceText }],
  summary: "Head entity could not be located.",
};
export const kgSchema: KGSchema = {
  id: "business",
  version: "1.0",
  entity_types: [
    { name: "Organization", description: "Company", aliases: {} },
    { name: "Product", description: "Product", aliases: {} },
  ],
  relations: [
    {
      name: "develops",
      description: "Develops",
      domain: ["Organization"],
      range: ["Product"],
    },
  ],
  rules: [],
  examples: [],
};
export const kgProfile: KGProfile = {
  id: "replay-demo",
  extractor: "replay",
  provider: "replay",
  model: "recorded-model",
  output_method: "json_schema",
  chunk_size: 4000,
  chunk_overlap: 200,
  max_output_tokens: 2048,
  temperature: 0,
};
export const kgRun: KGRun = {
  id: "kg-run-1",
  dataset_id: dataset.id,
  version_id: "version-1",
  schema_id: kgSchema.id,
  profile_id: kgProfile.id,
  model: kgProfile.model,
  extractor: "replay",
  status: "partial",
  created_at: "2026-10-24T00:00:00Z",
  report: {
    documents: 1,
    blocks: 2,
    cached: 0,
    extracted: 1,
    failed: 1,
    unexecuted: 0,
    model_calls: 2,
    entities: 2,
    relations: 2,
    verified: 1,
    needs_review: 1,
    entities_verified: 2,
    entities_needs_review: 0,
    relations_verified: 1,
    relations_needs_review: 1,
    input_tokens: 40,
    output_tokens: 20,
    cost_usd: null,
    accounted_cost_usd: "0",
    elapsed_seconds: 0.2,
    partial_documents: ["notes.txt"],
    failures: [
      {
        file_id: sourceRef.asset_id,
        filename: "notes.txt",
        start: 30,
        end: 60,
        reason: "length",
        attempted: true,
      },
    ],
    proposals: [
      {
        reason: "unknown_relation",
        count: 1,
        samples: [
          {
            head: "Cedar",
            relation: "invented",
            tail: "Reed",
            evidence: "Cedar develops Reed.",
          },
        ],
      },
    ],
  },
};
export const kgGraph: KGGraph = {
  nodes: [
    {
      id: "cedar",
      label: "Cedar",
      entity_type: "Organization",
      members: ["cedar", "cedar-alias"],
    },
    { id: "reed", label: "Reed", entity_type: "Product", members: ["reed"] },
  ],
  edges: [
    {
      id: "accepted-edge",
      source: "cedar",
      target: "reed",
      predicate: "kg.develops",
      status: "accepted",
      verification: "verified",
    },
    {
      id: "candidate-edge",
      source: "cedar",
      target: "reed",
      predicate: "kg.owns",
      status: "candidate",
      verification: "verified",
    },
    {
      id: "relation-review",
      source: "cedar",
      target: "reed",
      predicate: "kg.uses",
      status: "candidate",
      verification: "needs_review",
    },
  ],
  truncated: true,
};
export const kgPlan: ActionPlan = {
  ...actionPlan,
  action_type: "run_kg_extraction",
  external: true,
  impact: {
    ...actionPlan.impact,
    external: true,
    kg_estimate: {
      target_host: "model.example.com",
      model: "review-model",
      documents: 24,
      blocks: 30,
      input_tokens: 12000,
      max_output_tokens: 2048,
      cost_upper_usd: null,
    },
  },
};
