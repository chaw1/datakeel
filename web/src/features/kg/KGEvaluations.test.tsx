import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { KGEvaluations } from "./KGEvaluations";

import type { KGEvaluation } from "../../api/kg";

const prf = { p: 0.9, r: 0.8, f1: 0.847, tp: 9, fp: 1, fn: 2 };
const metrics: KGEvaluation["recording"]["all"] = {
  passages: 24,
  missing: [],
  errors: 0,
  relation_strict: prf,
  relation_pair: prf,
  entity_typed: prf,
  entity_untyped: prf,
  trap_hits: 3,
  pred_relations: 10,
  label_outside_schema: 0.1,
  endpoint_unmapped: 0,
  endpoint_in_text: 1,
  evidence_located: 1,
  verified_ratio: 0.9,
  failed_blocks: 0,
  latency_total_s: 1,
  latency_mean_s: 0.1,
};
const recording = { all: metrics, zh: metrics, en: metrics, verified: metrics };
const report: KGEvaluation = {
  suite: "text",
  id: "eval-1",
  blocked_relations: [],
  failures: [],
  metric_convention: "Independent benchmark",
  provider: "kg",
  schema_version: "1.0",
  created_at: "2026-10-24T00:00:00Z",
  profile: "replay-demo",
  model: "recorded-model",
  suite_digest: "suite-1",
  recording,
  product: {
    ...recording,
    all: {
      ...metrics,
      relation_strict: { ...prf, p: 0.95, r: 0.9, f1: 0.924 },
    },
  },
  elapsed_seconds: 0.2,
  input_tokens: 0,
  output_tokens: 0,
  cost_usd: null,
};

it("compares independent recording and product scores across saved runs", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify([
            report,
            { ...report, id: "eval-2", profile: "replay-flash" },
          ]),
        ),
      ),
    ),
  );
  const user = userEvent.setup();
  render(<KGEvaluations />);
  expect(
    await screen.findByText("replay-flash", { selector: "td" }),
  ).toBeVisible();
  expect(screen.getAllByText("0.950 / 0.900 / 0.924")).toHaveLength(2);
  await user.click(screen.getByText(/Evaluation details · replay-demo/));
  expect(screen.getAllByText("Chinese F1")[0]).toBeVisible();
  expect(screen.getAllByText("Typed entity F1")[0]).toBeVisible();
  expect(screen.getAllByText("Unknown")[0]).toBeVisible();
});

it("shows independent image scoring views, image groups and transcription quality", async () => {
  const group = {
    name: "A_clean",
    metrics,
    box_true_positives: 10,
    box_hits: 8,
    box_hit_rate: 0.8,
    cer: 0.025,
    identifier_preservation: 0.95,
    transcription_failures: 1,
  };
  const imageReport = {
    ...report,
    suite: "image",
    transcription_profile: "replay-image-demo",
    image_recording: {
      groups: [group, { ...group, name: "A_scan" }, { ...group, name: "B" }],
    },
    image_product: { groups: [{ ...group, box_hit_rate: 0.7 }] },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([imageReport])))),
  );
  render(<KGEvaluations />);
  const label = await screen.findByText("Image evaluation");
  const imageSection = label.closest("section");
  expect(imageSection).toHaveTextContent("Clear text");
  expect(imageSection).toHaveTextContent("Scanned text");
  expect(imageSection).toHaveTextContent("Diagrams");
  expect(imageSection).toHaveTextContent("80.0%");
  expect(imageSection).toHaveTextContent("70.0%");
  expect(imageSection).toHaveTextContent("2.50%");
  expect(imageSection).toHaveTextContent("95.0%");
});
