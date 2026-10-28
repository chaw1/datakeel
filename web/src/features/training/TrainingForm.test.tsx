import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { leakage, splitSet } from "./testFixtures";
import { TrainingForm } from "./TrainingForm";
import { TrainingLeakage } from "./TrainingLeakage";

it("validates ratio totals and accepts two sets with configurable thresholds", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(<TrainingForm busy={false} onSubmit={submit} />);
  await user.clear(screen.getByLabelText("Test"));
  await user.type(screen.getByLabelText("Test"), "0");
  expect(
    screen.getByRole("button", { name: "Save immutable split" }),
  ).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("total 1");
  await user.clear(screen.getByLabelText("Train"));
  await user.type(screen.getByLabelText("Train"), "0.9");
  await user.clear(screen.getByLabelText("Random seed"));
  await user.type(screen.getByLabelText("Random seed"), "7");
  await user.click(screen.getByLabelText("Balance labels across sets"));
  await user.clear(screen.getByLabelText("Text distance threshold"));
  await user.type(screen.getByLabelText("Text distance threshold"), "5");
  await user.click(
    screen.getByRole("button", { name: "Preview distribution" }),
  );
  expect(submit).toHaveBeenCalledWith(
    expect.objectContaining({
      ratios: { train: 0.9, val: 0.1, test: 0 },
      seed: 7,
      stratify: false,
      text_threshold: 5,
    }),
    true,
  );
});

it("requires an explicit leakage read and reports a clean result", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify({ ...leakage, pairs: [] }))),
  );
  vi.stubGlobal("fetch", fetch);
  render(<TrainingLeakage split={splitSet} />);
  expect(fetch).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Check leakage" }));
  await screen.findByRole("status");
  expect(
    screen.getByText(
      "No cross-set leakage found within the configured thresholds.",
    ),
  ).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/versions/version-1/training/splits/split-1/leakage",
    expect.objectContaining({ method: "GET" }),
  );
});

it("keeps disabled generated ratios out of directory split requests", async () => {
  const user = userEvent.setup();
  const submit = vi.fn();
  render(<TrainingForm busy={false} onSubmit={submit} />);
  await user.clear(screen.getByLabelText("Train"));
  await user.type(screen.getByLabelText("Train"), "0.5");
  expect(
    screen.getByRole("button", { name: "Save immutable split" }),
  ).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Split source"), "directory");
  await user.click(
    screen.getByRole("button", { name: "Save immutable split" }),
  );
  expect(submit).toHaveBeenCalledWith(
    expect.objectContaining({
      source: "directory",
      ratios: { train: 0.8, val: 0.1, test: 0.1 },
    }),
    false,
  );
});
