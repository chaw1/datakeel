import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { actionPlan, actionRun } from "../../test/actionFixtures";
import { dataset, file, version } from "../../test/fixtures";

import { evaluation, trainingRun } from "./testFixtures";
import { TrainingGovernance } from "./TrainingGovernance";

import type { TrainingRun } from "../../api/llmData";

const trainFile = { ...file, filename: "training.jsonl" };
const evalFile = { ...file, id: "evaluation-file", filename: "evaluation.txt" };
const plan = { ...actionPlan, action_type: "clean_training_data" as const };

function mockGovernance(initial: TrainingRun[] = [trainingRun]) {
  let reports = initial;
  let registered = [evaluation];
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    let payload: unknown = reports;
    if (path.endsWith("/evaluations")) {
      if (init?.method === "POST") {
        registered = [
          ...registered,
          { ...evaluation, id: "evaluation-2", name: "New evaluation" },
        ];
        payload = registered[1];
      } else payload = registered;
    }
    if (path.endsWith("/analyze")) {
      reports = [trainingRun];
      payload = trainingRun;
    }
    if (path.endsWith("/clean") || path.startsWith("/api/approvals/"))
      payload = plan;
    if (path.endsWith("/execute")) {
      reports = [{ ...trainingRun, cleaned_version_id: "cleaned-version" }];
      payload = { ...actionRun, action_type: "clean_training_data" };
    }
    return Promise.resolve(new Response(JSON.stringify(payload)));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

function panel(onChanged = vi.fn()) {
  return render(
    <TrainingGovernance
      datasetId={dataset.id}
      versions={[
        { ...version, manifest: [trainFile, evalFile] },
        { ...version, id: "version-older" },
      ]}
      files={[trainFile, evalFile]}
      onChanged={onChanged}
    />,
  );
}

it("loads bounded, redacted reports only after expanding the dataset section", async () => {
  const fetch = mockGovernance();
  const user = userEvent.setup();
  panel();
  expect(fetch).not.toHaveBeenCalled();
  await user.click(screen.getByText("Text data governance"));
  await screen.findByText("Language confidence 98% · estimated tokens 30");
  expect(document.querySelector(".llm-data-preview")).toHaveTextContent(
    "Please contact [EMAIL] for the generated sample.",
  );
  expect(screen.getAllByText("[EMAIL]", { selector: "mark" })[0]).toBeVisible();
  expect(screen.getByText("File file-1 · line 2")).toBeVisible();
  expect(
    screen.getByRole("region", { name: "Language distribution" }),
  ).toHaveTextContent("Mixed");
  expect(screen.getByText("Cluster 1 · 2 records")).toBeVisible();
  expect(screen.getByText("Evaluation entry evaluation-1:7")).toBeVisible();
  expect(
    screen.getByText(
      "Chosen is longer than rejected in 50.0% of 2 preference pairs.",
    ),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Download complete decision ledger" }),
  ).toHaveAttribute("href", "/api/training-governance/training-run-1/ledger");
  expect(fetch.mock.calls.every(([, init]) => init?.method === "GET")).toBe(
    true,
  );
});

it("previews configured cleaning, then signs the exact run before execution", async () => {
  const fetch = mockGovernance([]);
  const changed = vi.fn();
  const user = userEvent.setup();
  panel(changed);
  await user.click(screen.getByText("Text data governance"));
  await screen.findByText(
    "No report for this version. Run an analysis to preview issues and cleaning decisions.",
  );
  await user.click(screen.getByLabelText(evaluation.name));
  await user.selectOptions(screen.getByLabelText("Record format"), "messages");
  await user.clear(screen.getByLabelText("Maximum estimated tokens"));
  await user.type(screen.getByLabelText("Maximum estimated tokens"), "4096");
  await user.click(
    screen.getByRole("button", { name: "Analyze and preview cleaning" }),
  );
  await screen.findByText("Language confidence 98% · estimated tokens 30");
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/text-governance/analyze",
    expect.objectContaining({
      body: JSON.stringify({
        version_id: version.id,
        evaluation_ids: [evaluation.id],
        config: {
          format: "messages",
          max_tokens: 4096,
          contamination_ngram: 13,
        },
      }),
    }),
  );
  expect(
    fetch.mock.calls.some(
      ([path]) => path.endsWith("/clean") || path.endsWith("/execute"),
    ),
  ).toBe(false);
  await user.click(
    screen.getByRole("button", { name: "Review cleaning plan" }),
  );
  const approve = await screen.findByRole("button", {
    name: "Approve and create a cleaned training version",
  });
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  await user.click(approve);
  expect(
    await screen.findByText("Created dataset version cleaned-version"),
  ).toBeVisible();
  expect(
    await screen.findByText(
      "Cleaning completed. Open Versions to inspect the new manifest and Lineage to follow its receipt.",
    ),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "View lineage receipt" }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.findIndex(([path]) => path.startsWith("/api/approvals/")),
  ).toBeLessThan(
    fetch.mock.calls.findIndex(([path]) => path.endsWith("/execute")),
  );
  expect(changed).toHaveBeenCalledTimes(2);
});

it("invalidates the prepared plan when switching source versions", async () => {
  const fetch = mockGovernance();
  const user = userEvent.setup();
  panel();
  await user.click(screen.getByText("Text data governance"));
  await user.click(
    await screen.findByRole("button", { name: "Review cleaning plan" }),
  );
  await screen.findByRole("button", {
    name: "Approve and create a cleaned training version",
  });
  await user.selectOptions(
    screen.getByLabelText("Source dataset version"),
    "version-older",
  );
  expect(
    screen.queryByRole("button", {
      name: "Approve and create a cleaned training version",
    }),
  ).not.toBeInTheDocument();
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/datasets/dataset-1/text-governance?version_id=version-older",
      expect.anything(),
    );
  });
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});

it("registers an imported evaluation snapshot and selects it for the next dry run", async () => {
  const fetch = mockGovernance();
  const user = userEvent.setup();
  panel();
  await user.click(screen.getByText("Text data governance"));
  await screen.findByLabelText(evaluation.name);
  await user.click(screen.getByText("Register your evaluation set"));
  await user.type(
    screen.getByLabelText("Evaluation set name"),
    "New evaluation",
  );
  await user.click(screen.getByLabelText(evalFile.filename));
  await user.click(
    screen.getByRole("button", { name: "Register evaluation set" }),
  );
  expect(await screen.findByText("Evaluation set registered.")).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/text-governance/evaluations",
    expect.objectContaining({
      body: JSON.stringify({
        name: "New evaluation",
        source_dataset_id: dataset.id,
        version_id: version.id,
        file_ids: [evalFile.id],
      }),
    }),
  );
  expect(
    await screen.findByRole("checkbox", { name: "New evaluation" }),
  ).toBeChecked();
});

it("renders the same redacted findings with Chinese labels in the dark theme", async () => {
  mockGovernance();
  document.documentElement.dataset.theme = "dark";
  localStorage.setItem("datakeel.locale", "zh");
  const user = userEvent.setup();
  render(
    <I18nProvider>
      <TrainingGovernance
        datasetId={dataset.id}
        versions={[version]}
        files={[trainFile]}
        onChanged={vi.fn()}
      />
    </I18nProvider>,
  );
  await user.click(screen.getByText("文本数据治理"));
  const samples = await screen.findByRole("region", { name: "脱敏记录抽样" });
  expect(
    within(samples).getAllByText("[EMAIL]", { selector: "mark" })[0],
  ).toBeVisible();
  expect(screen.getByRole("region", { name: "语言分布" })).toHaveTextContent(
    "混合",
  );
  expect(screen.getByRole("button", { name: "审阅清洗计划" })).toBeVisible();
  delete document.documentElement.dataset.theme;
});

it("keeps an analysis failure visible and allows retry without preparing a write", async () => {
  const fetch = mockGovernance([]);
  fetch.mockImplementationOnce(() =>
    Promise.resolve(
      new Response(JSON.stringify({ detail: "Analysis unavailable" }), {
        status: 503,
      }),
    ),
  );
  panel();
  await userEvent.setup().click(screen.getByText("Text data governance"));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "503 Analysis unavailable",
  );
  await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => {
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  expect(
    fetch.mock.calls.some(
      ([path]) => path.endsWith("/clean") || path.endsWith("/execute"),
    ),
  ).toBe(false);
});
