import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";

import { splitSet } from "./testFixtures";
import { TrainingExport } from "./TrainingExport";

it("requires an author and locks the reviewed parameters while preparing", async () => {
  const user = userEvent.setup();
  const pending: { complete?: (response: Response) => void } = {};
  const fetch = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        pending.complete = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetch);
  const split = {
    ...splitSet,
    members: splitSet.members.map((member) => ({
      ...member,
      annotations: ["reviewer-a", "reviewer-b"].map((annotator) => ({
        sample_id: member.sample_id,
        annotator_id: annotator,
        labels: ["harbor"],
        boxes: [],
        spans: null,
        text_length: null,
        image_width: 100,
        image_height: 100,
      })),
    })),
  };
  render(<TrainingExport split={split} />);
  await user.type(screen.getByLabelText("Archive filename"), "training.tar.gz");
  expect(
    screen.getByRole("button", { name: "Review export plan" }),
  ).toBeDisabled();
  expect(fetch).not.toHaveBeenCalled();
  await user.selectOptions(
    screen.getByLabelText("Annotation author"),
    "reviewer-b",
  );
  await user.click(screen.getByRole("button", { name: "Review export plan" }));
  for (const label of [
    "Training format",
    "Annotation author",
    "Archive filename",
  ])
    expect(screen.getByLabelText(label)).toBeDisabled();
  await act(() => {
    pending.complete?.(
      new Response(
        JSON.stringify({ ...actionPlan, action_type: "export_dataset" }),
      ),
    );
  });
  await screen.findByRole("article", { name: "Action plan: export_dataset" });
  for (const label of [
    "Training format",
    "Annotation author",
    "Archive filename",
  ])
    expect(screen.getByLabelText(label)).toBeEnabled();
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/export_dataset/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: "dataset-1",
        version_id: "version-1",
        split_set_id: "split-1",
        format: "coco",
        destination: "training.tar.gz",
        annotator_id: "reviewer-b",
      }),
    }),
  );
});
