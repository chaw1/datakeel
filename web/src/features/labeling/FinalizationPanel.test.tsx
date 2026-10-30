import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";

import * as actions from "./actions";
import { FinalizationPanel } from "./FinalizationPanel";

vi.mock("./actions", () => ({
  prepareProduction: vi.fn(),
  executeProduction: vi.fn(),
}));
it("prepares finalization and waits for a separate human signature before execution", async () => {
  const plan = {
    ...actionPlan,
    id: "plan",
    plan_digest: "digest",
    canonical_params: { project_id: "project" },
    impact: { ...actionPlan.impact, object_count: 2 },
  };
  vi.mocked(actions.prepareProduction).mockResolvedValue(plan);
  const changed = vi.fn();
  render(<FinalizationPanel projectId="project" ready onChanged={changed} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Review finalization plan" }),
  );
  expect(
    await screen.findByRole("dialog", { name: "Finalize approved project" }),
  ).toBeVisible();
  expect(actions.executeProduction).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Approve and finalize project" }),
  );
  await waitFor(() => {
    expect(actions.executeProduction).toHaveBeenCalledWith(plan, true);
  });
  expect(changed).toHaveBeenCalledOnce();
});
it("disables finalization while any task is not approved", () => {
  render(
    <FinalizationPanel
      projectId="project"
      ready={false}
      onChanged={() => undefined}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Review finalization plan" }),
  ).toBeDisabled();
});

it("blocks an already prepared signature when the project stops being ready", async () => {
  vi.mocked(actions.prepareProduction).mockResolvedValue(actionPlan);
  const props = { projectId: "project", ready: true, onChanged: vi.fn() };
  const { rerender } = render(<FinalizationPanel {...props} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Review finalization plan" }),
  );
  const signature = await screen.findByRole("button", {
    name: "Approve and finalize project",
  });
  expect(signature).toBeEnabled();
  rerender(<FinalizationPanel {...props} ready={false} />);
  expect(signature).toBeDisabled();
  fireEvent.click(signature);
  expect(actions.executeProduction).not.toHaveBeenCalled();
  expect(props.onChanged).not.toHaveBeenCalled();
});

it("states the plan in plain words and keeps raw parameters under Details", () => {
  vi.mocked(actions.prepareProduction).mockResolvedValue({
    ...actionPlan,
    canonical_params: { project_id: "project" },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ name: "Harbour scenes" }), {
          headers: { "content-type": "application/json" },
        }),
      ),
    ),
  );
  render(
    <FinalizationPanel
      projectId="project"
      ready={false}
      summary={{
        tasks: 8,
        blocked: 2,
        datasetId: "dataset-1",
        versionId: "version-12345678",
      }}
      onChanged={vi.fn()}
    />,
  );
  expect(
    screen.getByText("2 tasks are not approved yet and block finalization"),
  ).toBeVisible();
  vi.unstubAllGlobals();
});

it("lists task count, target dataset and blockers once prepared", async () => {
  vi.mocked(actions.prepareProduction).mockResolvedValue({
    ...actionPlan,
    canonical_params: { project_id: "project" },
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ name: "Harbour scenes" }), {
          headers: { "content-type": "application/json" },
        }),
      ),
    ),
  );
  render(
    <FinalizationPanel
      projectId="project"
      ready
      summary={{
        tasks: 8,
        blocked: 0,
        datasetId: "dataset-1",
        versionId: "version-12345678",
      }}
      onChanged={vi.fn()}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Review finalization plan" }),
  );
  expect(await screen.findByText("Finalize 8 approved tasks")).toBeVisible();
  expect(
    await screen.findByText(
      "Write them into dataset “Harbour scenes” as a new version built on version version-",
    ),
  ).toBeVisible();
  expect(
    screen.getByText("Every task is approved; nothing blocks finalization"),
  ).toBeVisible();
  expect(screen.getByText("Details")).toBeVisible();
  expect(screen.getByText(/"project_id": "project"/)).not.toBeVisible();
  vi.unstubAllGlobals();
});
