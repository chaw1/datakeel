import { expect, it } from "vitest";

import { agentHref, contextFromQuery } from "./agentLink";

it("carries the project, task and selected rows of a page into the agent", () => {
  const href = agentHref(
    {
      project_id: "p-1",
      dataset_id: "d-1",
      task_id: "t-2",
      package_id: null,
      selected_kind: "production_task",
      selected_ids: ["t-2", "t-3"],
    },
    "把这两个任务分给小李",
  );
  expect(href.startsWith("#/agent?")).toBe(true);
  const query = new URLSearchParams(href.split("?")[1]);
  expect(query.get("prompt")).toBe("把这两个任务分给小李");
  expect(contextFromQuery(query)).toEqual({
    project_id: "p-1",
    dataset_id: "d-1",
    task_id: "t-2",
    selected_kind: "production_task",
    selected_ids: ["t-2", "t-3"],
  });
});

it("ignores selections of an unknown kind", () => {
  const query = new URLSearchParams(
    "project=p-1&selected_kind=nope&selected=a",
  );
  expect(contextFromQuery(query)).toEqual({
    project_id: "p-1",
    selected_ids: [],
  });
});
