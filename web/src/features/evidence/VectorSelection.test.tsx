import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { evidenceResult, sample } from "../../test/evidenceFixtures";
import { vectorGap, vectorResult } from "../../test/vectorFixtures";

import { EvidenceExplorer } from "./EvidenceExplorer";

it("adds a versioned gap only to the existing ObjectSet selection without preparing an action", async () => {
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("vector/query")
            ? vectorResult
            : path.includes("/assets/")
              ? { ...sample, assertions: [vectorGap] }
              : evidenceResult,
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <EvidenceExplorer
      datasetId={sample.dataset_id}
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await screen.findByRole("checkbox", { name: `Select ${sample.filename}` });
  await user.click(screen.getByText("Vector evidence"));
  await user.type(screen.getByLabelText("Task run ID"), "run-1");
  await user.click(
    screen.getByRole("button", { name: "Query run / restart pages" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Add gap to current selection" }),
  );
  expect(
    await screen.findByText(/Added to the current ObjectSet/),
  ).toBeVisible();
  expect(screen.getByText("1 selected")).toBeVisible();
  expect(screen.getByRole("button", { name: "Create version" })).toBeEnabled();
  expect(
    fetch.mock.calls.every(
      ([path]) => !path.includes("/actions/") && !path.includes("/decide"),
    ),
  ).toBe(true);
});

it("rejects a gap that was invalidated between display and manual selection", async () => {
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("vector/query")
            ? vectorResult
            : path.includes("/assets/")
              ? { ...sample, assertions: [] }
              : evidenceResult,
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <EvidenceExplorer
      datasetId={sample.dataset_id}
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(screen.getByText("Vector evidence"));
  await user.type(screen.getByLabelText("Task run ID"), "run-1");
  await user.click(
    screen.getByRole("button", { name: "Query run / restart pages" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Add gap to current selection" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "restart pagination",
  );
  expect(screen.getByRole("button", { name: "Create version" })).toBeDisabled();
});
