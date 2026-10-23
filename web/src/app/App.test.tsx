import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { metric } from "../features/catalog/fixtures";
import { mockObjects } from "../features/object/testFixtures";
import { I18nProvider } from "../i18n/I18nProvider";
import { dataset, task } from "../test/fixtures";

import App from "./App";

function mockWorkspace() {
  const objects = mockObjects().getMockImplementation();
  if (!objects) throw new Error("Object fixture missing");
  const fetch = vi.fn((path: string) => {
    let payload: unknown;
    if (path === "/api/approvals" || path === "/api/actions/runs") payload = [];
    else if (path === "/api/tasks") payload = [task];
    else if (path === "/api/datasets?include=quality")
      payload = [{ ...dataset, quality_score: 59 }];
    else if (path.startsWith("/api/search"))
      payload = [
        {
          kind: "metric",
          id: metric.definition.id,
          name: metric.definition.name,
        },
        { kind: "dataset", id: dataset.id, name: dataset.name },
      ];
    else return objects(path);
    return Promise.resolve(new Response(JSON.stringify(payload)));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("opens the workbench, six navigation groups, dataset archive and persisted language", async () => {
  mockWorkspace();
  const user = userEvent.setup();
  render(
    <I18nProvider>
      <App />
    </I18nProvider>,
  );
  expect(
    await screen.findByRole("heading", { level: 1, name: /Workbench/ }),
  ).toBeVisible();
  expect(document.querySelectorAll("[data-nav-group]")).toHaveLength(6);
  await user.click(screen.getByRole("link", { name: "Data library" }));
  await user.click(
    await screen.findByRole("button", { name: /Sample collection/ }),
  );
  expect(
    await screen.findByRole("heading", { level: 1, name: dataset.name }),
  ).toBeVisible();
  await user.click(screen.getByRole("link", { name: "Files 2" }));
  expect(
    await screen.findByRole("link", { name: "Download sample.txt" }),
  ).toBeVisible();
  expect(window.location.hash).toContain("/object/dataset/dataset-1?tab=files");
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Language" }),
    "zh",
  );
  expect(
    await screen.findByRole("navigation", { name: "对象档案" }),
  ).toBeVisible();
  expect(document.documentElement.lang).toBe("zh");
  expect(localStorage.getItem("datakeel.locale")).toBe("zh");
});

it("shows a retry action when the API is unavailable", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("offline"))),
  );
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to reach the API",
  );
  expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
});

it("redirects a legacy receipt URL to the matching object relation event", async () => {
  window.history.replaceState(
    null,
    "",
    "/#lineage?dataset=dataset-1&asset=output&event=event-1",
  );
  mockWorkspace();
  render(<App />);
  expect(
    await screen.findByRole("region", { name: "Lineage event details" }),
  ).toHaveTextContent("text.clean");
  await waitFor(() => {
    expect(window.location.hash).toContain(
      "#/object/dataset/dataset-1?tab=relations",
    );
  });
  expect(window.location.hash).toContain("event=event-1");
});

it("restores a direct catalog link without loading file dataset details", async () => {
  window.history.replaceState(
    null,
    "",
    `/#lineage?asset_id=${metric.definition.id}&include_catalog=true`,
  );
  const fetch = mockWorkspace();
  render(<App />);
  expect(
    await screen.findByRole("heading", {
      level: 1,
      name: metric.definition.name,
    }),
  ).toBeVisible();
  expect(window.location.hash).toContain(
    `#/object/metric/${metric.definition.id}?tab=relations`,
  );
  const calls = fetch.mock.calls.map(([path]) => path);
  expect(
    calls.some(
      (path) =>
        path.startsWith("/api/lineage/graph?asset_id=") &&
        path.includes("collapse=true"),
    ),
  ).toBe(true);
  expect(calls.some((path) => path.includes("/datasets/dataset-1/"))).toBe(
    false,
  );
  expect(screen.queryByText("No dataset selected")).not.toBeInTheDocument();
});
