import { webcrypto } from "node:crypto";

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { actionRun } from "../../test/actionFixtures";
import { dataset, file, version } from "../../test/fixtures";
import { column, metric, table, term } from "../catalog/fixtures";

import { objectHref, readObjectTarget } from "./navigation";
import { ObjectPage } from "./ObjectPage";
import { mockObjects } from "./testFixtures";

import type { ObjectTarget } from "./navigation";

const scrollIntoView = vi.fn();
beforeEach(() => {
  mockObjects();
  vi.stubGlobal("crypto", webcrypto);
  HTMLElement.prototype.scrollIntoView = scrollIntoView;
});
it.each([
  ["dataset", dataset.id, dataset.name, "Versioned"],
  ["file", file.id, "processed.txt", "Available"],
  ["version", version.id, `${dataset.name} · 1`, "Current"],
  ["action_run", actionRun.id, actionRun.action_type, "Succeeded"],
  ["table", table.asset_ref.asset_id, table.name, "Imported"],
  ["column", column.asset_ref.asset_id, column.name, "Imported"],
  ["metric", metric.definition.id, metric.definition.name, "Ready to query"],
  ["term", term.asset_ref.asset_id, term.name, "Unlinked"],
] as const)(
  "renders the shared %s archive header and usable relations",
  async (kind, id, name, status) => {
    render(<ObjectPage target={{ kind, id }} />);
    expect(
      await screen.findByRole("heading", { level: 1, name }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Copy ID" })).toHaveTextContent(
      id.slice(0, 8),
    );
    expect(
      within(
        screen.getByRole("article", { name: "Object archive" }),
      ).getAllByText(status).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "Relations" })).toBeVisible();
  },
);
it("copies the complete ID while showing its short form", async () => {
  const user = userEvent.setup();
  render(<ObjectPage target={{ kind: "dataset", id: dataset.id }} />);
  await screen.findByRole("heading", { level: 1, name: dataset.name });
  await user.click(screen.getByRole("button", { name: "Copy ID" }));
  expect(await navigator.clipboard.readText()).toBe(dataset.id);
  expect(screen.getByRole("button", { name: "Copy ID" })).toHaveTextContent(
    "Copied",
  );
});
it("opens the dataset datasheet from the shared object tabs", async () => {
  const user = userEvent.setup();
  const onOpen = vi.fn<(target: ObjectTarget) => void>();
  render(
    <ObjectPage target={{ kind: "dataset", id: dataset.id }} onOpen={onOpen} />,
  );
  await user.click(await screen.findByRole("link", { name: "Datasheet" }));
  expect(onOpen).toHaveBeenCalledWith(
    expect.objectContaining({
      kind: "dataset",
      id: dataset.id,
      tab: "datasheets",
    }),
  );
});
it("links dataset facts to the current version, files, quality, candidates, and event", async () => {
  const user = userEvent.setup();
  const onOpen = vi.fn<(target: ObjectTarget) => void>();
  render(
    <ObjectPage target={{ kind: "dataset", id: dataset.id }} onOpen={onOpen} />,
  );
  const facts = await screen.findByRole("region", { name: "Facts" });
  await user.click(
    within(facts).getByRole("link", { name: "Current version 1" }),
  );
  expect(onOpen).toHaveBeenLastCalledWith(
    expect.objectContaining({
      kind: "version",
      id: version.id,
      datasetId: dataset.id,
    }),
  );
  for (const [name, tab] of [
    ["Files 2", "files"],
    ["Quality score 83.5", "quality"],
    ["Candidate assertions 0", "evidence"],
  ]) {
    await user.click(within(facts).getByRole("link", { name }));
    expect(onOpen).toHaveBeenLastCalledWith(
      expect.objectContaining({ id: dataset.id, tab }),
    );
  }
  const updated = within(facts).getByRole("link", { name: /^Updated/ });
  expect(readObjectTarget(updated.getAttribute("href") ?? "")?.eventId).toBe(
    "event-1",
  );
});
it("maps table and metric facts to their exact fields and relationship filters", async () => {
  const { rerender } = render(
    <ObjectPage target={{ kind: "table", id: table.asset_ref.asset_id }} />,
  );
  let facts = await screen.findByRole("region", { name: "Facts" });
  expect(
    readObjectTarget(
      within(facts)
        .getByRole("link", { name: "Fields 2" })
        .getAttribute("href") ?? "",
    ),
  ).toMatchObject({ tab: "evidence", section: "fields" });
  expect(
    within(facts).getByRole("link", { name: "Consuming metrics 1" }),
  ).toHaveAttribute(
    "href",
    expect.stringContaining("table=ecommerce%2Fmain%2Forders"),
  );
  expect(
    readObjectTarget(
      within(facts)
        .getByRole("link", { name: /^Imported/ })
        .getAttribute("href") ?? "",
    )?.eventId,
  ).toBe("catalog-import-1");
  rerender(
    <ObjectPage target={{ kind: "metric", id: metric.definition.id }} />,
  );
  await screen.findByRole("heading", {
    level: 1,
    name: metric.definition.name,
  });
  facts = screen.getByRole("region", { name: "Facts" });
  expect(
    readObjectTarget(
      within(facts)
        .getByRole("link", { name: "Dimensions 1" })
        .getAttribute("href") ?? "",
    ),
  ).toMatchObject({ tab: "relations", relation: "sliced_by" });
  expect(
    readObjectTarget(
      within(facts)
        .getByRole("link", { name: "Referenced fields 3" })
        .getAttribute("href") ?? "",
    ),
  ).toMatchObject({ relation: "measures" });
});
it("locates and expands a historical receipt event", async () => {
  render(
    <ObjectPage
      target={{
        kind: "dataset",
        id: dataset.id,
        tab: "history",
        eventId: "event-1",
      }}
    />,
  );
  await waitFor(() => {
    expect(document.getElementById("object-event-event-1")).toHaveClass(
      "is-focused",
    );
  });
  expect(
    document.querySelector("#object-event-event-1 details"),
  ).toHaveAttribute("open");
});
it("keeps the object route when following a report chapter", async () => {
  const user = userEvent.setup();
  const target: ObjectTarget = {
    kind: "dataset",
    id: dataset.id,
    tab: "report",
  };
  window.history.replaceState(null, "", objectHref(target));
  render(<ObjectPage target={target} />);
  await user.click(
    await screen.findByRole("link", { name: "01 Dataset summary" }),
  );
  expect(window.location.hash).toBe(objectHref(target));
  expect(scrollIntoView).toHaveBeenCalled();
});
it("opens version files pinned to their immutable manifest", async () => {
  render(
    <ObjectPage
      target={{
        kind: "version",
        id: version.id,
        datasetId: dataset.id,
        tab: "files",
      }}
    />,
  );
  const download = await screen.findByRole("link", {
    name: "Download processed.txt",
  });
  expect(download).toHaveAttribute(
    "href",
    expect.stringContaining("?version=version-1"),
  );
});

it.each([
  ["dataset", dataset.id],
  ["file", file.id],
] as const)(
  "keeps %s chat drafts bound to the displayed object's dataset",
  async (kind, id) => {
    render(<ObjectPage target={{ kind, id }} />);
    const link = await screen.findByRole("link", {
      name: "Start conversation",
    });
    const params = new URLSearchParams(
      link.getAttribute("href")?.split("?")[1],
    );
    expect(params.get("dataset")).toBe(dataset.id);
    expect(params.get("prompt")).toContain(id);
  },
);

it("opens text data governance from dataset tabs and retains the source version", async () => {
  const user = userEvent.setup();
  const onOpen = vi.fn<(target: ObjectTarget) => void>();
  render(
    <ObjectPage target={{ kind: "dataset", id: dataset.id }} onOpen={onOpen} />,
  );
  await user.click(
    await screen.findByRole("link", { name: "Text data governance" }),
  );
  expect(onOpen).toHaveBeenCalledWith(
    expect.objectContaining({
      kind: "dataset",
      id: dataset.id,
      tab: "text-governance",
    }),
  );
});
