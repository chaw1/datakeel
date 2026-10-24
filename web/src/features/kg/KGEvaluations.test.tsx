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
