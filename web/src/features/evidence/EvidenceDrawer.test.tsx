import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import * as evidenceApi from "../../api/evidence";
import { actionRun } from "../../test/actionFixtures";
import { sample } from "../../test/evidenceFixtures";

import { EvidenceDrawer } from "./EvidenceDrawer";

afterEach(() => {
  vi.restoreAllMocks();
});

it("loads the displayed source version, reviews all three statuses, and preserves the drawer", async () => {
  let detail = sample;
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(detail))),
  );
  vi.stubGlobal("fetch", fetch);
  const decide = vi
    .spyOn(evidenceApi, "decideAssertion")
    .mockImplementation((id, status) => {
      detail = {
        ...detail,
        assertions: detail.assertions.map((item) =>
          item.id === id ? { ...item, status } : item,
        ),
      };
      return Promise.resolve({
        ...actionRun,
        action_type: "decide_assertions",
      });
    });
  const reviewed = vi.fn();
  const user = userEvent.setup();
  render(
    <EvidenceDrawer
      sample={sample}
      onClose={vi.fn()}
      onReviewed={reviewed}
      onOpenGraph={vi.fn()}
    />,
  );
  const card = await screen.findByRole("article", {
    name: "mentions: mention-1",
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/evidence/assets/image-1?version_id=source-1",
    expect.anything(),
  );
  for (const [label, status] of [
    ["Accept assertion", "accepted"],
    ["Reject assertion", "rejected"],
    ["Restore candidate", "candidate"],
  ] as const) {
    await user.click(within(card).getByRole("button", { name: label }));
    await waitFor(() => {
      expect(card).toHaveClass(status);
    });
    await waitFor(() => {
      expect(within(card).getByRole("button", { name: label })).toBeDisabled();
    });
  }
  expect(decide).toHaveBeenCalledTimes(3);
  expect(reviewed).toHaveBeenCalledTimes(3);
  expect(
    screen.getByRole("dialog", { name: "Sample evidence details" }),
  ).toBeVisible();
  expect(
    screen.getByText(
      "Decision saved. The extraction evidence remains unchanged.",
    ),
  ).toBeVisible();
});

it("locates a text anchor, links to the existing semantic graph, and closes on cancel", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(sample)))),
  );
  const open = vi.fn();
  const close = vi.fn();
  const user = userEvent.setup();
  render(
    <EvidenceDrawer
      sample={sample}
      onClose={close}
      onReviewed={vi.fn()}
      onOpenGraph={open}
    />,
  );
  const card = await screen.findByRole("article", {
    name: "mentions: mention-1",
  });
  await user.click(
    within(card).getByRole("button", { name: "Locate evidence" }),
  );
  expect(screen.getByText("person", { selector: "mark" })).toBeVisible();
  const link = screen.getByRole("link", { name: "View evidence subgraph" });
  expect(link).toHaveAttribute(
    "href",
    expect.stringContaining("asset_id=image-1"),
  );
  await user.click(link);
  expect(open).toHaveBeenCalledWith({
    datasetId: sample.dataset_id,
    assetId: "image-1",
    includeSemantic: true,
  });
  fireEvent(
    screen.getByRole("dialog"),
    new Event("cancel", { cancelable: true }),
  );
  expect(close).toHaveBeenCalledOnce();
});

it("moves between assertions and reviews the selected assertion with j/k/a/r", async () => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  let detail = sample;
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(detail)))),
  );
  const decide = vi
    .spyOn(evidenceApi, "decideAssertion")
    .mockImplementation((id, status) => {
      detail = {
        ...detail,
        assertions: detail.assertions.map((item) =>
          item.id === id ? { ...item, status } : item,
        ),
      };
      return Promise.resolve({
        ...actionRun,
        action_type: "decide_assertions",
      });
    });
  const close = vi.fn();
  render(
    <EvidenceDrawer
      sample={sample}
      onClose={close}
      onReviewed={vi.fn()}
      onOpenGraph={vi.fn()}
    />,
  );
  const mention = await screen.findByRole("article", {
    name: "mentions: mention-1",
  });
  const annotation = screen.getByRole("article", {
    name: "annotated_as: annotation-1",
  });
  const dialog = screen.getByRole("dialog");
  fireEvent.keyDown(dialog, { key: "j" });
  expect(annotation).toHaveClass("is-active");
  fireEvent.keyDown(dialog, { key: "k" });
  expect(mention).toHaveClass("is-active");
  for (const [key, status] of [
    ["a", "accepted"],
    ["r", "rejected"],
  ]) {
    fireEvent.keyDown(dialog, { key });
    await waitFor(() => {
      expect(mention).toHaveClass(status);
    });
    await waitFor(() => {
      expect(
        within(mention).getByRole("button", { name: "Restore candidate" }),
      ).toBeEnabled();
    });
    expect(decide).toHaveBeenLastCalledWith(
      "mention-1",
      status,
      expect.any(String),
    );
  }
  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
});

it("suppresses every shortcut and Enter for native and start/end composition states", async () => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(sample)))),
  );
  const decide = vi.spyOn(evidenceApi, "decideAssertion");
  const close = vi.fn();
  render(
    <EvidenceDrawer
      sample={sample}
      onClose={close}
      onReviewed={vi.fn()}
      onOpenGraph={vi.fn()}
    />,
  );
  const mention = await screen.findByRole("article", {
    name: "mentions: mention-1",
  });
  const dialog = screen.getByRole("dialog");
  fireEvent.compositionStart(dialog);
  for (const key of ["j", "k", "a", "r", "Escape", "Enter"])
    expect(fireEvent.keyDown(dialog, { key, cancelable: true })).toBe(
      key !== "Enter" && key !== "Escape",
    );
  fireEvent(dialog, new Event("cancel", { cancelable: true }));
  const button = within(mention).getByRole("button", {
    name: "Accept assertion",
  });
  expect(fireEvent.keyDown(button, { key: " ", cancelable: true })).toBe(false);
  expect(fireEvent.keyDown(dialog, { key: "x", cancelable: true })).toBe(true);
  fireEvent.compositionEnd(dialog);
  for (const key of ["j", "k", "a", "r", "Escape", "Enter"])
    expect(
      fireEvent.keyDown(dialog, { key, isComposing: true, cancelable: true }),
    ).toBe(key !== "Enter" && key !== "Escape");
  expect(mention).toHaveClass("is-active");
  expect(decide).not.toHaveBeenCalled();
  expect(close).not.toHaveBeenCalled();
  fireEvent.keyDown(dialog, { key: "j" });
  expect(
    screen.getByRole("article", { name: "annotated_as: annotation-1" }),
  ).toHaveClass("is-active");
});

it("cancels the native Escape default while composing even without a compositionstart event", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(sample)))),
  );
  const close = vi.fn();
  render(
    <EvidenceDrawer
      sample={sample}
      onClose={close}
      onReviewed={vi.fn()}
      onOpenGraph={vi.fn()}
    />,
  );
  await screen.findByRole("article", { name: "mentions: mention-1" });
  const dialog = screen.getByRole("dialog");
  const allowed = fireEvent.keyDown(dialog, {
    key: "Escape",
    isComposing: true,
    cancelable: true,
  });
  if (allowed) fireEvent(dialog, new Event("cancel", { cancelable: true }));
  expect(allowed).toBe(false);
  expect(close).not.toHaveBeenCalled();
  expect(dialog).toBeVisible();
  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(close).toHaveBeenCalledOnce();
});
