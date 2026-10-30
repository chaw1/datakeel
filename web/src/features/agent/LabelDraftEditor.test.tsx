import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";

import { LabelDraftEditor } from "./LabelDraftEditor";

import type { LabelSet } from "../../api/intents";

const draft: LabelSet = {
  id: "vehicles",
  version: 1,
  name: "Vehicles",
  published: false,
  previous_version: null,
  migration: [],
  affected_annotations: 0,
  affected_revisions: 0,
  created_at: "2026-10-31T00:00:00Z",
  published_at: null,
  labels: [
    { id: "car", name: "轿车", name_zh: "轿车", name_en: "Car" },
    { id: "bus", name: "公交", name_zh: "公交", name_en: "Bus" },
  ],
  guidelines: {
    overview_zh: "框住整辆车",
    overview_en: "Box the whole vehicle",
    rules: [
      {
        label_id: "car",
        text_zh: "只标完整可见的车",
        text_en: "Only fully visible cars",
        examples: [
          { sample_id: "file-7", kind: "positive", note: "clear car" },
          { sample_id: "file-9", kind: "negative", note: "truck" },
        ],
      },
    ],
  },
  draft_source: {
    standard_codes: ["VEHICLE_TYPE"],
    label_set_ids: [],
    annotation_dataset_ids: [],
    dataset_id: "d1",
    version_id: "v1",
    sample_ids: ["file-7", "file-9"],
    profile: "offline",
    model: "offline-rules",
    input_tokens: 0,
    output_tokens: 0,
    cost_usd: 0,
    plan_id: "plan-draft",
    drafted_at: "2026-10-31T00:00:00Z",
    dropped_examples: 0,
  },
};
const props = {
  labelSetId: "vehicles",
  version: 1,
  onPublished: vi.fn(),
  onOpenReceipt: vi.fn(),
};
function stub() {
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/production/objects/label_set"))
      return Promise.resolve(
        Response.json({
          function: "production_objects",
          data: [{ properties: draft }],
        }),
      );
    if (init?.method === "POST")
      return Promise.resolve(
        Response.json({
          ...actionPlan,
          action_type: url.includes("publish")
            ? "publish_label_set"
            : "create_label_set",
        }),
      );
    return Promise.resolve(Response.json([]));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
afterEach(() => {
  vi.unstubAllGlobals();
});

it("shows names, guidelines, cited samples and where the draft came from", async () => {
  stub();
  render(<LabelDraftEditor {...props} />);
  expect(await screen.findByDisplayValue("轿车")).toBeVisible();
  expect(screen.getByDisplayValue("Only fully visible cars")).toBeVisible();
  expect(screen.getByText("file-7")).toBeVisible();
  expect(screen.getByText("Negative")).toBeVisible();
  expect(screen.getByText(/offline-rules from 2 samples/)).toBeVisible();
  expect(screen.getByText(/VEHICLE_TYPE/)).toBeVisible();
});

it("saves edits as a prepared update and publishes only through a signed plan", async () => {
  const fetch = stub();
  render(<LabelDraftEditor {...props} />);
  const english = await screen.findByLabelText("English name of bus");
  await userEvent.clear(english);
  await userEvent.type(english, "City bus");
  await userEvent.click(screen.getByRole("button", { name: "Save edits" }));
  const save = fetch.mock.calls.find(([url]) =>
    url.endsWith("/api/actions/create_label_set/prepare"),
  );
  const body = JSON.parse(save?.[1]?.body as string) as {
    operation: string;
    labels: { id: string; name_en: string }[];
  };
  expect(body.operation).toBe("update");
  expect(body.labels.find((item) => item.id === "bus")?.name_en).toBe(
    "City bus",
  );
  expect(await screen.findByText(/nothing is written before/)).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Publish…" }));
  expect(
    fetch.mock.calls.some(([url]) =>
      url.endsWith("/api/actions/publish_label_set/prepare"),
    ),
  ).toBeTruthy();
  expect(
    fetch.mock.calls.some(([url]) => url.includes("/execute")),
  ).toBeFalsy();
});
