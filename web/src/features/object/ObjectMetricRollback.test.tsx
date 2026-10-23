import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { metric, metricPlan, metricRun } from "../catalog/fixtures";

import { ObjectPage } from "./ObjectPage";
import { mockObjects } from "./testFixtures";

it("refreshes the metric archive and its history to the newly created version after rollback", async () => {
  const fetch = mockObjects();
  const fallback = fetch.getMockImplementation();
  let currentVersion = 2;
  fetch.mockImplementation((path, init) => {
    if (path === "/api/actions/rollback_metric/prepare")
      return Promise.resolve(
        new Response(
          JSON.stringify({
            ...metricPlan,
            action_type: "rollback_metric",
            canonical_params: { metric_id: metric.definition.id, version: 1 },
          }),
        ),
      );
    if (path.endsWith("/execute")) {
      currentVersion = 3;
      return Promise.resolve(
        new Response(
          JSON.stringify({ ...metricRun, action_type: "rollback_metric" }),
        ),
      );
    }
    if (path.startsWith("/api/catalog/metrics/"))
      return Promise.resolve(
        new Response(
          JSON.stringify(
            path.endsWith("/history")
              ? {
                  metric_id: metric.definition.id,
                  versions: Array.from({ length: currentVersion }, (_, i) => ({
                    ...metric,
                    definition: { ...metric.definition, version: i + 1 },
                  })),
                  audit: [],
                }
              : {
                  ...metric,
                  definition: { ...metric.definition, version: currentVersion },
                },
          ),
        ),
      );
    if (!fallback) throw new Error("Missing fixture response");
    return fallback(path, init);
  });
  const changed = vi.fn();
  const user = userEvent.setup();
  const { container } = render(
    <ObjectPage
      target={{ kind: "metric", id: metric.definition.id, tab: "history" }}
      onDataChanged={changed}
    />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Roll back to this version" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Execute action" }),
  );
  await waitFor(() => {
    expect(
      container.querySelector('[data-metric-version="3"]'),
    ).toHaveTextContent("Current version");
  });
  const facts = screen.getByRole("region", { name: "Facts" });
  expect(within(facts).getByRole("link", { name: "Version 3" })).toBeVisible();
  expect(changed).toHaveBeenCalledOnce();
  expect(
    screen.getByRole("heading", { name: "Definition revisions · 3" }),
  ).toBeVisible();
  expect(
    screen.getAllByRole("button", { name: "Roll back to this version" }),
  ).toHaveLength(2);
});
