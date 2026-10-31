import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import { I18nContext, translator } from "../../../i18n/context";
import { labelingProject } from "../../../test/labelingFixtures";

import { PrelabelPanel } from "./PrelabelPanel";

import type { ProjectWorkbench } from "../../../api/production";

const measured: ProjectWorkbench = {
  ...labelingProject,
  prelabel_accuracy: {
    project_id: "project",
    assessed_tasks: 4,
    exact_match_tasks: 1,
    exact_match_rate: 0.25,
    iou_50: {
      threshold: 0.5,
      model_objects: 10,
      human_objects: 8,
      true_positives: 7,
      precision: 0.7,
      recall: 0.875,
      f1: 0.7778,
      all_hit_tasks: 2,
      all_hit_rate: 0.5,
    },
    iou_75: {
      threshold: 0.75,
      model_objects: 10,
      human_objects: 8,
      true_positives: 5,
      precision: 0.5,
      recall: 0.625,
      f1: 0.5556,
      all_hit_tasks: 1,
      all_hit_rate: 0.25,
    },
    attribute_agreement: {
      matched_objects: 7,
      consistent_objects: 6,
      rate: 6 / 7,
    },
  },
  confidence_thresholds: {
    high: 0.9,
    low: 0.4,
    source: "calibrated",
    objects: 48,
    minimum_objects: 30,
    notes: [],
    tiers: [
      { tier: "high", objects: 30, hits: 29, rate: 29 / 30 },
      { tier: "medium", objects: 12, hits: 9, rate: 0.75 },
      { tier: "low", objects: 6, hits: 2, rate: 1 / 3 },
    ],
    segments: [
      { low: 0.12, high: 0.4, objects: 6, hits: 2, rate: 1 / 3 },
      { low: 0.4, high: 0.9, objects: 12, hits: 9, rate: 0.75 },
      { low: 0.9, high: 0.99, objects: 30, hits: 29, rate: 29 / 30 },
    ],
    pass_through: true,
  },
  prelabel_spend: [
    {
      model_id: "model-1",
      model_name: "qwen-vl",
      model_version: "2026-10",
      currency: "CNY",
      runs: 2,
      images: 14,
      input_tokens: 123456,
      output_tokens: 2048,
      cost: 0.01234,
    },
  ],
};

it("headlines F1 at IoU 0.5 and explains the one-to-one matching rule with both thresholds", () => {
  render(<PrelabelPanel data={measured} />);
  const headline = screen.getByText("78%").closest("p");
  expect(headline).toHaveTextContent("78% F1 at IoU 0.5");
  const tip = headline?.getAttribute("title") ?? "";
  expect(tip).toContain("paired one-to-one by descending IoU, as in COCO");
  expect(tip).toContain("IoU 0.5: precision 70%, recall 88%, F1 78%");
  expect(tip).toContain("IoU 0.75: precision 50%, recall 63%, F1 56%");
  expect(tip).toContain("Tasks with every object hit at IoU 0.5: 50% (2/4)");
  expect(tip).toContain("Matched objects with identical attributes: 86% (6/7)");
  expect(headline).toHaveAccessibleDescription(
    /a pair with IoU ≥ 0.5 is a hit/,
  );
  expect(screen.getByText("Exact-match rate: 25%")).toBeVisible();
  expect(screen.getByText("Approved reference: 1/4 tasks")).toBeVisible();
});

it("shows thresholds, where they came from and the measured hit rate per tier", () => {
  render(<PrelabelPanel data={measured} />);
  expect(screen.getByText("0.90")).toBeVisible();
  expect(screen.getByText("0.40")).toBeVisible();
  expect(screen.getByText("Measured from approved data")).toBeVisible();
  expect(screen.getByText("Basis: 48 reviewed model objects")).toBeVisible();
  const tiers = screen.getByRole("table", { name: "Confidence tiers" });
  expect(
    within(tiers).getByRole("row", { name: "medium tier 12 9 75%" }),
  ).toBeVisible();
  expect(
    within(tiers).getByRole("row", { name: "low tier 6 2 33%" }),
  ).toBeVisible();
  expect(
    screen.queryByText("Not enough reviewed samples; using defaults"),
  ).toBeNull();
  expect(screen.queryByText(/not passed straight to review/)).toBeNull();
});

it("shows the calibration curve the thresholds were read from and the rule in one line", () => {
  render(<PrelabelPanel data={measured} />);
  const curve = screen.getByRole("table", { name: "Calibration curve" });
  expect(
    within(curve).getByRole("row", {
      name: "Confidence range Objects Hits Hit rate",
    }),
  ).toBeVisible();
  expect(
    within(curve).getByRole("row", { name: "0.12–0.40 6 2 33%" }),
  ).toBeVisible();
  expect(
    within(curve).getByRole("row", { name: "0.90–0.99 30 29 97%" }),
  ).toBeVisible();
  expect(
    screen.getByText(/the lowest confidence with a calibrated hit rate ≥ 95%/),
  ).toHaveClass("muted");
});

it("says in plain words when too few reviewed objects exist and defaults apply", () => {
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: () => undefined, t: translator("zh") }}
    >
      <PrelabelPanel
        data={{
          ...measured,
          confidence_thresholds: {
            high: 0.85,
            low: 0.5,
            source: "default",
            objects: 12,
            minimum_objects: 30,
            notes: ["insufficient_samples"],
            tiers: [],
            segments: [],
            pass_through: false,
          },
        }}
      />
    </I18nContext.Provider>,
  );
  expect(screen.getByText("样本不足，用默认值")).toBeVisible();
  expect(screen.getByText("12/30 个对象")).toBeVisible();
  expect(screen.getByText("默认值")).toBeVisible();
  expect(
    screen.getByText("样本不足，暂不直通：高档草稿先留给人改"),
  ).toBeVisible();
  expect(screen.queryByRole("table", { name: "校准曲线" })).toBeNull();
});

it("lists spend per model and keeps empty facts readable", () => {
  const { rerender } = render(<PrelabelPanel data={measured} />);
  const spend = screen.getByRole("table", { name: "Prelabel spend by model" });
  expect(
    within(spend).getByRole("row", {
      name: "qwen-vl@2026-10 2 14 123,456 2,048 0.0123 CNY",
    }),
  ).toBeVisible();
  rerender(<PrelabelPanel data={labelingProject} />);
  expect(
    screen.getByText("No model has spent anything on this project yet."),
  ).toBeVisible();
  expect(
    screen.getByText("No tier thresholds for this project yet."),
  ).toBeVisible();
  expect(screen.getByText("Not measured").closest("p")).toHaveTextContent(
    "Not measured F1 at IoU 0.5",
  );
});
