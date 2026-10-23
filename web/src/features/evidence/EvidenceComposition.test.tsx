import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import { evidenceResult, sample } from "../../test/evidenceFixtures";

import { EvidenceExplorer } from "./EvidenceExplorer";

it.each([
  ["create_version_from_selection", "Create version"],
  ["quarantine_files", "Quarantine selection"],
  ["delete_files", "Delete selection"],
])(
  "does not prepare or execute %s during composition",
  async (action, name) => {
    const fetch = vi.fn((path: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path.endsWith("/prepare")
              ? {
                  ...actionPlan,
                  action_type: action,
                  reversible: action !== "delete_files",
                }
              : path.endsWith("/execute")
                ? { ...actionRun, action_type: action }
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
    await user.click(
      await screen.findByRole("checkbox", {
        name: `Select ${sample.filename}`,
      }),
    );
    const button = screen.getByRole("button", { name });
    fireEvent.compositionStart(button);
    await user.click(button);
    expect(
      fetch.mock.calls.filter(([path]) => path.startsWith("/api/actions/")),
    ).toHaveLength(0);
    fireEvent.compositionEnd(button);
    expect(fireEvent.keyDown(button, { key: "Enter", isComposing: true })).toBe(
      false,
    );
    expect(fireEvent.keyDown(button, { key: " ", keyCode: 229 })).toBe(false);
    await user.click(button);
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        `/api/actions/${action}/prepare`,
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(
      fetch.mock.calls.filter(([path]) => path.endsWith("/prepare")),
    ).toHaveLength(1);
    if (action === "delete_files") {
      expect(
        await screen.findByRole("button", { name: "Approve and delete files" }),
      ).toBeVisible();
      expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
        false,
      );
    } else {
      expect(
        await screen.findByRole("region", { name: "Receipt" }),
      ).toBeVisible();
      expect(
        fetch.mock.calls.filter(([path]) => path.endsWith("/execute")),
      ).toHaveLength(1);
    }
  },
);
