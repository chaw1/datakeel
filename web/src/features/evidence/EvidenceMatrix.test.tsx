import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { annotation, mention, sample } from "../../test/evidenceFixtures";

import { EvidenceResults } from "./EvidenceResults";

it("orders matrix source letters left to right and links each to its matching footer", () => {
  const gap = {
    ...mention,
    id: "gap-1",
    predicate: "label_gap",
    extractor: { id: "evidence.label_gap", version: "1.0" },
  };
  const { container } = render(
    <EvidenceResults
      items={[{ ...sample, assertions: [annotation, gap, mention] }]}
      selected={[]}
      onSelect={vi.fn()}
      onInspect={vi.fn()}
    />,
  );
  const matrix = screen.getByRole("table", { name: "Assertion matrix" });
  const references = within(matrix).getAllByRole("link");
  expect(references.map((link) => link.textContent)).toEqual(["a", "b", "c"]);
  const footnotes = [...container.querySelectorAll(".source-footnotes > li")];
  expect(
    footnotes.map(
      (item) => item.querySelector(".footnote-marker")?.textContent,
    ),
  ).toEqual(["a", "b", "c"]);
  for (const [index, reference] of references.entries()) {
    expect(reference).toHaveAttribute("href", `#${footnotes[index].id}`);
    expect(footnotes[index]).toHaveTextContent(
      [mention, annotation, gap][index].extractor.id,
    );
  }
});

it("links the same numbered concept across a matrix cell, caption and image region", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <EvidenceResults
      items={[sample]}
      selected={[]}
      onSelect={vi.fn()}
      onInspect={vi.fn()}
    />,
  );
  const matrix = screen.getByRole("table", { name: "Assertion matrix" });
  await user.hover(
    within(matrix).getByRole("button", { name: "person · Mentions" }),
  );
  const caption = container.querySelector(".evidence-anchor");
  const box = container.querySelector(".annotation-box");
  const row = matrix.querySelector(":scope > tbody > tr");
  expect(caption).toHaveClass("is-linked");
  expect(box).toHaveClass("is-linked");
  expect(row).toHaveClass("is-linked");
  for (const element of [caption, box, row])
    expect(element).toHaveAttribute("data-anchor-number", "1");
  await user.unhover(
    within(matrix).getByRole("button", { name: "person · Mentions" }),
  );
  expect(box).not.toHaveClass("is-linked");
});
it("deduplicates source footnotes and the common version while showing honest missing cells and candidate totals", () => {
  const second = {
    ...sample,
    asset_ref: { ...sample.asset_ref, asset_id: "second-image" },
    filename: "val/second.png",
  };
  const { container } = render(
    <EvidenceResults
      items={[sample, second]}
      selected={[]}
      onSelect={vi.fn()}
      onInspect={vi.fn()}
    />,
  );
  expect(container.querySelectorAll(".source-footnotes > li")).toHaveLength(2);
  expect(screen.getAllByText("source-1", { exact: true })).toHaveLength(1);
  expect(
    screen.getAllByRole("img", { name: "No assertion recorded" }),
  ).toHaveLength(2);
  expect(
    screen.getAllByRole("button", { name: "2 candidates to review" }),
  ).toHaveLength(2);
});
it("hides unit confidence but shows measured uncertainty", () => {
  const value = {
    ...sample,
    assertions: sample.assertions.map((assertion, index) => ({
      ...assertion,
      confidence: index ? 0.6 : 1,
    })),
  };
  render(
    <EvidenceResults
      items={[value]}
      selected={[]}
      onSelect={vi.fn()}
      onInspect={vi.fn()}
    />,
  );
  expect(screen.getByText("60%")).toBeVisible();
  expect(screen.queryByText("100%")).not.toBeInTheDocument();
});

it("distinguishes mixed source versions and lets the drawer own the only footnote list", () => {
  const second = {
    ...sample,
    asset_ref: { ...sample.asset_ref, asset_id: "second-image" },
    filename: "val/second.png",
    source_version: "source-2",
  };
  const { container, rerender } = render(
    <EvidenceResults
      items={[sample, second]}
      selected={[]}
      onSelect={vi.fn()}
      onInspect={vi.fn()}
    />,
  );
  expect(container.querySelectorAll(".source-footnotes > li")).toHaveLength(4);
  const references = screen
    .getAllByRole("table", { name: "Assertion matrix" })
    .map((matrix) => within(matrix).getAllByRole("link"));
  expect(
    references.map((links) => links.map((link) => link.textContent)),
  ).toEqual([
    ["a", "c"],
    ["b", "d"],
  ]);
  for (const links of references)
    for (const link of links) {
      const target = document.getElementById(
        link.getAttribute("href")?.slice(1) ?? "",
      );
      expect(target?.querySelector(".footnote-marker")?.textContent).toBe(
        link.textContent,
      );
    }
  expect(
    screen.getByText("evidence.caption_mentions · 1.0 · source-1"),
  ).toBeVisible();
  expect(
    screen.getByText("evidence.caption_mentions · 1.0 · source-2"),
  ).toBeVisible();
  expect(
    container.querySelector(".evidence-source-version"),
  ).not.toBeInTheDocument();
  rerender(
    <EvidenceResults
      items={[sample, second]}
      selected={[]}
      onSelect={vi.fn()}
      onInspect={vi.fn()}
      showFootnotes={false}
    />,
  );
  expect(container.querySelector(".source-footnotes")).not.toBeInTheDocument();
});
it("keeps caption anchors visible in the compact matrix even when other concepts need review first", () => {
  const value = {
    ...sample,
    assertions: [
      ...["car", "cat", "dog", "bike"].map((concept) => ({
        ...sample.assertions[0],
        id: concept,
        object: { concept, value: "unknown" as const },
        anchors: [],
      })),
      ...sample.assertions,
    ],
  };
  render(
    <EvidenceResults
      items={[value]}
      selected={[]}
      onSelect={vi.fn()}
      onInspect={vi.fn()}
    />,
  );
  const matrix = screen.getByRole("table", { name: "Assertion matrix" });
  expect(
    within(matrix).getByRole("button", { name: "person · Mentions" }),
  ).toBeVisible();
  expect(matrix.querySelector(":scope > tbody > tr")).toHaveAttribute(
    "data-anchor-id",
    "person",
  );
});
