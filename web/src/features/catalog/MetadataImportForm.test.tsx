import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { MetadataImportForm } from "./MetadataImportForm";

import type { MetadataImportReport } from "../../api/metadataImports";

function reply() {
  const report: MetadataImportReport = {
    object_count: 4,
    new: 2,
    changed: 1,
    deleted: 1,
    unchanged: 0,
    drafts: 1,
    link_count: 2,
    snapshot_version: 2,
    failed_sql_count: 0,
    parse_failures: [],
  };
  const fetch = vi
    .fn()
    .mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(report))),
    );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("reads dbt JSON locally, posts contents, and shows the incremental summary", async () => {
  const fetch = reply();
  const user = userEvent.setup();
  const imported = vi.fn();
  render(<MetadataImportForm onImported={imported} />);
  await user.type(screen.getByLabelText("Source ID"), "shop");
  const manifest = {
    metadata: {
      dbt_schema_version: "https://schemas.getdbt.com/dbt/manifest/v12.json",
    },
    nodes: {},
  };
  await user.upload(
    screen.getByLabelText("manifest.json (required)"),
    new File([JSON.stringify(manifest)], "manifest.json", {
      type: "application/json",
    }),
  );
  expect(screen.getByLabelText("Source ID")).toBeValid();
  expect(screen.getByLabelText("manifest.json (required)")).toBeValid();
  await user.click(screen.getByRole("button", { name: "Import artifacts" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "New 2 · Changed 1 · Deleted at source 1 · Unchanged 0 · Metric drafts 1",
  );
  expect(imported).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledWith(
    "/api/catalog/import/dbt",
    expect.objectContaining({
      body: JSON.stringify({ source_id: "shop", name: "dbt", manifest }),
    }),
  );
});

it("rejects unsupported manifest versions before any HTTP import", async () => {
  const fetch = reply();
  const user = userEvent.setup();
  render(<MetadataImportForm onImported={vi.fn()} />);
  await user.type(screen.getByLabelText("Source ID"), "shop");
  await user.upload(
    screen.getByLabelText("manifest.json (required)"),
    new File(
      [
        '{"metadata":{"dbt_schema_version":"https://schemas.getdbt.com/dbt/manifest/v9.json"}}',
      ],
      "manifest.json",
      { type: "application/json" },
    ),
  );
  await user.click(screen.getByRole("button", { name: "Import artifacts" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Only dbt manifest versions 10, 11, and 12 are supported.",
  );
  expect(fetch).not.toHaveBeenCalled();
});

it("rejects non-object Airflow JSON locally and imports a corrected export", async () => {
  const fetch = reply();
  const user = userEvent.setup();
  render(<MetadataImportForm onImported={vi.fn()} />);
  await user.selectOptions(screen.getByLabelText("Metadata format"), "airflow");
  await user.type(screen.getByLabelText("Source ID"), "scheduler");
  const input = screen.getByLabelText("Airflow DAG JSON (required)");
  await user.upload(
    input,
    new File(["[]"], "bad.json", { type: "application/json" }),
  );
  await user.click(screen.getByRole("button", { name: "Import artifacts" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "bad.json must contain a JSON object.",
  );
  expect(fetch).not.toHaveBeenCalled();
  await user.upload(
    input,
    new File(['{"dags":[]}'], "dags.json", { type: "application/json" }),
  );
  await user.click(screen.getByRole("button", { name: "Import artifacts" }));
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledOnce();
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/catalog/import/airflow",
    expect.objectContaining({
      body: '{"source_id":"scheduler","name":"Airflow","document":{"dags":[]}}',
    }),
  );
});

it("shows a server validation failure without reporting success", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response('{"detail":"Malformed DAG export"}', { status: 422 }),
      ),
  );
  const user = userEvent.setup();
  const imported = vi.fn();
  render(<MetadataImportForm onImported={imported} />);
  await user.selectOptions(screen.getByLabelText("Metadata format"), "airflow");
  await user.type(screen.getByLabelText("Source ID"), "scheduler");
  await user.upload(
    screen.getByLabelText("Airflow DAG JSON (required)"),
    new File(['{"dags":{}}'], "dags.json", { type: "application/json" }),
  );
  await user.click(screen.getByRole("button", { name: "Import artifacts" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "422 Malformed DAG export",
  );
  expect(imported).not.toHaveBeenCalled();
});

it("requires a JSON file with an accessible validation message", async () => {
  const fetch = reply();
  const user = userEvent.setup();
  render(<MetadataImportForm onImported={vi.fn()} />);
  await user.type(screen.getByLabelText("Source ID"), "shop");
  await user.click(screen.getByRole("button", { name: "Import artifacts" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Choose a required JSON file.",
  );
  expect(fetch).not.toHaveBeenCalled();
});
