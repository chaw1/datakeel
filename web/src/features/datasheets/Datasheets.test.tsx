import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan, actionRun } from "../../test/actionFixtures";
import { version } from "../../test/fixtures";

import { Datasheets } from "./Datasheets";
import { sheet } from "./testFixtures";

it("prepares and executes an offline draft without an approval decision", async () => {
  const user = userEvent.setup();
  let saved = false;
  const plan = {
    ...actionPlan,
    action_type: "generate_datasheet",
    reversible: true,
  };
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (path.endsWith("/execute")) {
      saved = true;
      return Promise.resolve(
        new Response(
          JSON.stringify({ ...actionRun, action_type: "generate_datasheet" }),
        ),
      );
    }
    return Promise.resolve(
      new Response(
        JSON.stringify(init?.method === "POST" ? plan : saved ? [sheet] : []),
      ),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<Datasheets datasetId="dataset-1" versions={[version]} />);
  await screen.findByText("No datasheet exists for this version and language.");
  await user.click(screen.getByRole("button", { name: "Generate draft" }));
  await user.click(
    await screen.findByRole("button", { name: "Execute action" }),
  );
  await screen.findByRole("link", { name: "Download Markdown" });
  expect(
    fetch.mock.calls.some(([path]) => path.startsWith("/api/approvals/")),
  ).toBe(false);
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/datasheets",
    expect.objectContaining({
      body: JSON.stringify({
        version_id: "version-1",
        language: "en",
        mode: "template",
      }),
    }),
  );
});

it("requires publication approval before executing the frozen plan", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/datasheets")
            ? [sheet]
            : path.endsWith("/execute")
              ? { ...actionRun, action_type: "publish_datasheet" }
              : {
                  ...actionPlan,
                  action_type: "publish_datasheet",
                  reversible: false,
                },
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<Datasheets datasetId="dataset-1" versions={[version]} />);
  await user.click(
    await screen.findByRole("button", { name: "Publish datasheet" }),
  );
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  await user.click(
    await screen.findByRole("button", {
      name: "Approve and publish the datasheet",
    }),
  );
  await waitFor(() => {
    expect(fetch.mock.calls.map(([path]) => path)).toContain(
      "/api/actions/plan-1/execute",
    );
  });
  const paths = fetch.mock.calls.map(([path]) => path);
  expect(paths.indexOf("/api/approvals/plan-1")).toBeLessThan(
    paths.indexOf("/api/actions/plan-1/execute"),
  );
});

it("selects history by version and compares saved documents with stale status", async () => {
  const user = userEvent.setup();
  const old = {
    ...sheet,
    id: "sheet-old",
    version_id: "version-old",
    stale: true,
    created_at: "2026-10-26T00:00:00Z",
  };
  const comparison = {
    before_id: "sheet-old",
    after_id: "sheet-1",
    changes: [
      {
        fact_id: "fact-name",
        before: "Old collection",
        after: "Sample collection",
        kind: "changed",
      },
    ],
    changed_chapters: ["composition"],
  };
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(path.includes("/compare/") ? comparison : [sheet, old]),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <Datasheets
      datasetId="dataset-1"
      versions={[version, { ...version, id: "version-old" }]}
    />,
  );
  await screen.findByRole("link", { name: "Download Markdown" });
  await user.selectOptions(
    screen.getByLabelText("Compare with a saved datasheet"),
    "sheet-old",
  );
  expect(
    screen.getByRole("heading", { name: "Previous datasheet" }),
  ).toBeVisible();
  await screen.findByText("Changed chapters: Composition");
  expect(screen.getByText("Old collection")).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasheets/sheet-old/compare/sheet-1",
    expect.anything(),
  );
  expect(screen.getByText("Out of date")).toBeVisible();
  await user.selectOptions(
    screen.getByLabelText("Dataset version"),
    "version-old",
  );
  expect(
    screen.queryByRole("heading", { name: "Previous datasheet" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Download Markdown" }),
  ).toHaveAttribute(
    "href",
    "/api/datasheets/sheet-old/download?format=markdown",
  );
  expect(
    screen.getByRole("button", { name: "Regenerate for selected version" }),
  ).toBeVisible();
});

it("passes language and explicit model selection into a controlled generation plan", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string, init?: RequestInit) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          init?.method === "POST"
            ? { ...actionPlan, action_type: "generate_datasheet" }
            : [],
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<Datasheets datasetId="dataset-1" versions={[version]} />);
  await user.selectOptions(screen.getByLabelText("Document language"), "zh");
  await user.selectOptions(screen.getByLabelText("Writing method"), "model");
  await user.selectOptions(screen.getByLabelText("Provider"), "openai");
  await user.type(screen.getByLabelText("Model"), "configured-model");
  await user.click(screen.getByRole("button", { name: "Generate draft" }));
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/datasheets",
    expect.objectContaining({
      body: JSON.stringify({
        version_id: "version-1",
        language: "zh",
        mode: "model",
        provider: "openai",
        model: "configured-model",
      }),
    }),
  );
});

it("regenerates a stale document for the latest version with one action", async () => {
  const user = userEvent.setup();
  const old = {
    ...sheet,
    id: "sheet-old",
    version_id: "version-old",
    stale: true,
  };
  const fetch = vi.fn((path: string, init?: RequestInit) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/versions")
            ? [
                version,
                {
                  ...version,
                  id: "version-old",
                  created_at: version.created_at - 1,
                },
              ]
            : init?.method === "POST"
              ? {
                  ...actionPlan,
                  action_type: "generate_datasheet",
                  reversible: true,
                }
              : [old],
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <Datasheets
      datasetId="dataset-1"
      versions={[{ ...version, id: "version-old" }]}
      initialVersionId="version-old"
    />,
  );
  await user.click(
    await screen.findByRole("button", {
      name: "Regenerate for latest version",
    }),
  );
  await waitFor(() => {
    expect(screen.getByLabelText("Dataset version")).toHaveValue("version-1");
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/datasheets",
    expect.objectContaining({
      body: JSON.stringify({
        version_id: "version-1",
        language: "en",
        mode: "template",
      }),
    }),
  );
});
