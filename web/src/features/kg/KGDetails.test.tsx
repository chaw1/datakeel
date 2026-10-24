import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import {
  cedar,
  explanation,
  kgGraph,
  relation,
  sourceRef,
  sourceText,
} from "../../test/kgFixtures";

import { KGEntityDrawer } from "./KGEntityDrawer";
import { KGGraphPanel } from "./KGGraphPanel";
import { KGRelationDrawer } from "./KGRelationDrawer";

it("explains the missing endpoint and highlights evidence and tail with NFC codepoint spans", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(explanation)))),
  );
  render(<KGRelationDrawer assertionId="relation-review" onClose={vi.fn()} />);
  expect(
    await screen.findByText(
      "The head entity could not be located in the source. (Head entity)",
    ),
  ).toBeVisible();
  expect(screen.getByText("No verified span")).toBeVisible();
  const highlights = Array.from(
    document.querySelectorAll("mark"),
    (node) => node.textContent,
  );
  expect(highlights.join("")).toBe("Cedar develops Reed.");
  expect(
    document.querySelector('[data-anchor-number="1,3"] mark'),
  ).toHaveTextContent("Reed");
  expect(document.querySelector('[data-anchor-number="1,2"]')).toBeNull();
  expect(document.querySelector(".anchor-text")).toHaveTextContent("🚀 café");
});
it("highlights all three roles for verified relations and restores close behavior", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ ...explanation, relation })),
      ),
    ),
  );
  const close = vi.fn();
  const user = userEvent.setup();
  render(<KGRelationDrawer assertionId="relation-good" onClose={close} />);
  await screen.findByText("notes.txt");
  expect(
    document.querySelector('[data-anchor-number="1,2"] mark'),
  ).toHaveTextContent("Cedar");
  expect(
    document.querySelector('[data-anchor-number="1,3"] mark'),
  ).toHaveTextContent("Reed");
  await user.click(screen.getByRole("button", { name: "Close graph details" }));
  expect(close).toHaveBeenCalledOnce();
});
it("shows every entity occurrence from the frozen version source", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(
      new Response(
        JSON.stringify({
          asset_ref: sourceRef,
          filename: "notes.txt",
          text: sourceText,
        }),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <KGEntityDrawer entity={cedar} versionId="version-1" onClose={vi.fn()} />,
  );
  await screen.findByText("notes.txt");
  expect(
    Array.from(document.querySelectorAll("mark"), (node) => node.textContent),
  ).toEqual(["Cedar", "Cedar"]);
  expect(screen.getByText("Characters 7–12")).toBeVisible();
  expect(screen.getByText("Characters 28–33")).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/kg/sources/notes-1?version_id=version-1",
    expect.anything(),
  );
});
it("renders bounded graph states, accepted alias membership, and edge inspection", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(kgGraph))),
  );
  vi.stubGlobal("fetch", fetch);
  const inspect = vi.fn();
  const user = userEvent.setup();
  render(
    <KGGraphPanel
      query={{ dataset_id: "dataset-1", limit: 200 }}
      revision={0}
      onInspect={inspect}
    />,
  );
  await screen.findByText(
    "Results are bounded. Narrow the filters to inspect more of the graph.",
  );
  expect(document.querySelector(".kg-edge.accepted")).not.toBeNull();
  expect(document.querySelector(".kg-edge.candidate")).not.toBeNull();
  expect(document.querySelector(".kg-edge.needs_review")).not.toBeNull();
  expect(
    screen.getByText("2 entity identities", { selector: "text" }),
  ).toBeVisible();
  await user.click(screen.getByLabelText("Inspect relation: kg.uses"));
  expect(inspect).toHaveBeenCalledWith("relation-review");
  expect(fetch).toHaveBeenCalledWith(
    "/api/kg/graph",
    expect.objectContaining({
      body: JSON.stringify({ dataset_id: "dataset-1", limit: 60 }),
    }),
  );
});
it("renders Chinese review explanations", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(explanation)))),
  );
  render(
    <I18nProvider>
      <KGRelationDrawer assertionId="relation-review" onClose={vi.fn()} />
    </I18nProvider>,
  );
  const dialog = screen.getByRole("dialog");
  expect(
    await within(dialog).findByText(/头实体未能在原文中定位/),
  ).toBeVisible();
});

it("keeps each merged document's role offsets separate", async () => {
  const detail = relation.assertion.verification_detail;
  const merged = {
    ...explanation,
    relation: {
      ...relation,
      assertion: {
        ...relation.assertion,
        verification_detail: {
          ...detail,
          issues: [],
          locations: [
            {
              source: sourceRef,
              evidence: { type: "text_span", start: 7, end: 27 },
              head: { type: "text_span", start: 7, end: 12 },
              tail: { type: "text_span", start: 22, end: 26 },
              issues: [],
            },
            {
              source: { ...sourceRef, asset_id: "notes-2" },
              evidence: { type: "text_span", start: 0, end: 20 },
              head: { type: "text_span", start: 0, end: 5 },
              tail: { type: "text_span", start: 15, end: 19 },
              issues: [],
            },
          ],
        },
      },
    },
    sources: [
      ...explanation.sources,
      {
        asset_ref: { ...sourceRef, asset_id: "notes-2" },
        filename: "other.txt",
        text: "Cedar develops Reed.",
      },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(merged)))),
  );
  render(<KGRelationDrawer assertionId="relation-good" onClose={vi.fn()} />);
  await screen.findByText("other.txt");
  const documents = document.querySelectorAll(".kg-source");
  expect(documents).toHaveLength(2);
  for (const source of documents) {
    expect(
      source.querySelector('[data-anchor-number="1,2"] mark'),
    ).toHaveTextContent("Cedar");
    expect(
      source.querySelector('[data-anchor-number="1,3"] mark'),
    ).toHaveTextContent("Reed");
  }
});
