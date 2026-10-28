import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";

import { splitSet } from "./testFixtures";
import { TrainingExport } from "./TrainingExport";

it("freezes the version, split and selected format before an approved export", async () => {
  const user = userEvent.setup();
  const plan = {
    ...actionPlan,
    action_type: "export_dataset",
    reversible: false,
  };
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/execute")
            ? { ...actionRun, action_type: "export_dataset" }
            : plan,
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<TrainingExport split={splitSet} />);
  await user.selectOptions(screen.getByLabelText("Training format"), "yolo");
  await user.type(screen.getByLabelText("Archive filename"), "training.tar.gz");
  await user.click(screen.getByRole("button", { name: "Review export plan" }));
  await screen.findByRole("article", { name: "Action plan: export_dataset" });
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/export_dataset/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: "dataset-1",
        version_id: "version-1",
        split_set_id: "split-1",
        format: "yolo",
        destination: "training.tar.gz",
      }),
    }),
  );
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  await user.click(screen.getByRole("button", { name: /Approve and export/ }));
  const link = await screen.findByRole("link", {
    name: "Download training archive",
  });
  expect(link).toHaveAttribute("href", "/api/actions/plan-1/export");
  const paths = fetch.mock.calls.map(([path]) => path);
  expect(paths.indexOf("/api/approvals/plan-1")).toBeLessThan(
    paths.indexOf("/api/actions/plan-1/execute"),
  );
});

it("invalidates a frozen plan when its export format changes", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ ...actionPlan, action_type: "export_dataset" }),
        ),
      ),
    ),
  );
  render(<TrainingExport split={splitSet} />);
  await user.type(screen.getByLabelText("Archive filename"), "training.tar.gz");
  await user.click(screen.getByRole("button", { name: "Review export plan" }));
  await screen.findByRole("article", { name: "Action plan: export_dataset" });
  await user.selectOptions(
    screen.getByLabelText("Training format"),
    "text_jsonl",
  );
  expect(
    screen.queryByRole("article", { name: "Action plan: export_dataset" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Download training archive" }),
  ).not.toBeInTheDocument();
});

it("shows export preparation failures without creating a download link", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "No detection annotations" }), {
          status: 422,
        }),
      ),
    ),
  );
  render(<TrainingExport split={splitSet} />);
  await user.type(screen.getByLabelText("Archive filename"), "training.tar.gz");
  await user.click(screen.getByRole("button", { name: "Review export plan" }));
  await waitFor(() => {
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No detection annotations",
    );
  });
  expect(
    screen.queryByRole("link", { name: "Download training archive" }),
  ).not.toBeInTheDocument();
});
