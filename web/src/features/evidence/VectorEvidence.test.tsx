import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { actionRun } from "../../test/actionFixtures";
import { vectorGap, vectorResult } from "../../test/vectorFixtures";

import { VectorEvidence } from "./VectorEvidence";

it("queries four kinds and uses the opaque cursor only after explicit navigation", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(vectorResult))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const add = vi.fn(() => Promise.resolve());
  render(
    <VectorEvidence datasetId="dataset-1" onAdd={add} onReviewed={vi.fn()} />,
  );
  expect(fetch).not.toHaveBeenCalled();
  await user.click(screen.getByText("Vector evidence"));
  await user.type(screen.getByLabelText("Task run ID"), "run-1");
  expect(
    screen.getByLabelText("Result kind").querySelectorAll("option"),
  ).toHaveLength(4);
  await user.selectOptions(screen.getByLabelText("Result kind"), "coverage");
  await user.click(
    screen.getByRole("button", { name: "Query run / restart pages" }),
  );
  expect(await screen.findByText("0.2")).toBeVisible();
  expect(screen.getByText("0.8")).toBeVisible();
  expect(screen.getAllByText(/Partial success/).length).toBeGreaterThan(0);
  expect(screen.getByText("3 / 2 / 1 / 0")).toBeVisible();
  expect(add).not.toHaveBeenCalled();
  const button = screen.getByRole("button", {
    name: "Add gap to current selection",
  });
  button.focus();
  await user.keyboard("{Enter}");
  await waitFor(() => {
    expect(add).toHaveBeenCalledExactlyOnceWith(vectorGap);
  });
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(await screen.findByText(/No action executed/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Next page" }));
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/evidence/vector/query",
    expect.objectContaining<Record<string, unknown>>({
      body: expect.stringContaining('"cursor":"signed-page-2"'),
    }),
  );
  await screen.findByText("0.2");
  await user.click(screen.getByRole("button", { name: "Previous page" }));
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/evidence/vector/query",
    expect.objectContaining<Record<string, unknown>>({
      body: expect.stringContaining('"cursor":null'),
    }),
  );
});

it("keeps failure visible and restarts pagination after explicit human review", async () => {
  let fail = false;
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("decide")
            ? actionRun
            : fail
              ? { detail: "vector_cursor_invalid_or_stale" }
              : vectorResult,
        ),
        { status: fail ? 422 : 200 },
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const reviewed = vi.fn();
  render(
    <VectorEvidence
      datasetId="dataset-1"
      onAdd={vi.fn()}
      onReviewed={reviewed}
    />,
  );
  await user.click(screen.getByText("Vector evidence"));
  await user.type(screen.getByLabelText("Task run ID"), "run-1");
  await user.click(
    screen.getByRole("button", { name: "Query run / restart pages" }),
  );
  await user.click(await screen.findByRole("button", { name: "Accepted" }));
  await waitFor(() => {
    expect(reviewed).toHaveBeenCalledOnce();
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/evidence/assertions/decide",
    expect.objectContaining<Record<string, unknown>>({
      body: expect.stringContaining('"assertion_ids":["gap-1"]'),
    }),
  );
  await screen.findByText("0.2");
  fail = true;
  await user.click(screen.getByRole("button", { name: "Next page" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "vector_cursor_invalid_or_stale",
  );
  expect(screen.queryByText("0.2")).not.toBeInTheDocument();
});

it("provides Chinese controls and prevents stale gaps from entering selection", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ ...vectorResult, status: "stale" })),
      ),
    ),
  );
  const user = userEvent.setup();
  render(
    <I18nProvider>
      <VectorEvidence
        datasetId="dataset-1"
        onAdd={vi.fn()}
        onReviewed={vi.fn()}
      />
    </I18nProvider>,
  );
  await user.click(screen.getByText("向量证据"));
  await user.type(screen.getByLabelText("任务 run ID"), "run-1");
  await user.click(screen.getByRole("button", { name: "查询 run / 重新分页" }));
  expect(await screen.findByText(/证据已失效/)).toBeVisible();
  expect(
    screen.getByRole("button", { name: "将缺口加入当前选择" }),
  ).toBeDisabled();
  expect(screen.getByText("余弦相似度")).toBeVisible();
});
