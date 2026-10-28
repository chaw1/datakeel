import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { dataset, file, version } from "../../test/fixtures";

import { VersionCompare } from "./VersionCompare";

const versions = [{ ...version, id: "new-version" }, version];
const summary = {
  annotation_count: 4,
  label_count: 3,
  quality_score: 88,
  evidence_decisions: { accepted: 2 },
};
const categoryLabels = [
  ["added", "Added"],
  ["removed", "Removed"],
  ["content_changed", "Content changed"],
  ["metadata_changed", "Metadata only"],
  ["unchanged", "Unchanged"],
] as const;

it("shows five change counts and summary deltas and requests bounded category pages", async () => {
  const fetch = vi.fn((path: string) => {
    const query = new URL(path, "http://localhost").searchParams;
    const category = query.get("category") ?? "added";
    const offset = Number(query.get("offset"));
    return Promise.resolve(
      new Response(
        JSON.stringify({
          dataset_id: dataset.id,
          before_version: version.id,
          after_version: "new-version",
          counts: {
            added: 51,
            removed: 2,
            content_changed: 3,
            metadata_changed: 4,
            unchanged: 5,
          },
          files: [
            {
              category,
              file_id: `${category}-${String(offset)}`,
              before: category === "added" ? null : file,
              after:
                category === "removed"
                  ? null
                  : { ...file, filename: `${category}-${String(offset)}.txt` },
            },
          ],
          before_summary: { ...summary, annotation_count: 1 },
          after_summary: summary,
          next_offset: category === "added" && !offset ? 50 : null,
        }),
      ),
    );
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<VersionCompare versions={versions} datasetId={dataset.id} />);
  await user.click(screen.getByRole("button", { name: "Compare versions" }));
  expect(await screen.findByText("added-0.txt")).toBeVisible();
  expect(screen.getByText("1 → 4")).toBeVisible();
  for (const [category, label] of categoryLabels) {
    const count = {
      added: 51,
      removed: 2,
      content_changed: 3,
      metadata_changed: 4,
      unchanged: 5,
    }[category];
    expect(
      screen.getByRole("button", { name: `${label} · ${String(count)}` }),
    ).toBeVisible();
  }
  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByText("added-50.txt")).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    expect.stringContaining("offset=50&limit=50"),
    expect.anything(),
  );
  for (const [category, label] of categoryLabels.slice(1)) {
    await user.click(
      screen.getByRole("button", { name: new RegExp(`^${label} ·`) }),
    );
    await waitFor(() => {
      expect(fetch).toHaveBeenLastCalledWith(
        expect.stringContaining(`category=${category}&offset=0`),
        expect.anything(),
      );
    });
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  }
});

it("requires two distinct versions and reports a failed comparison", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ detail: "Version missing" }), {
        status: 404,
      }),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const { rerender } = render(
    <VersionCompare versions={[version]} datasetId={dataset.id} />,
  );
  expect(
    screen.getByRole("button", { name: "Compare versions" }),
  ).toBeDisabled();
  rerender(<VersionCompare versions={versions} datasetId={dataset.id} />);
  await user.selectOptions(
    screen.getByLabelText("After version"),
    "new-version",
  );
  await user.click(screen.getByRole("button", { name: "Compare versions" }));
  expect(await screen.findByText("404 Version missing")).toBeVisible();
});
