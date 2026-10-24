import {
  createEvent,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AskAnswerView } from "./AskAnswerView";
import {
  knowledgeAnswer,
  ownerKnowledge,
  shipmentSubject,
} from "./knowledgeFixtures";
import { KnowledgeResolution } from "./KnowledgeResolution";

it("selects a typed knowledge subject and protects IME Enter confirmation", async () => {
  const user = userEvent.setup();
  const choose = vi.fn();
  render(
    <KnowledgeResolution
      answer={{
        ...knowledgeAnswer,
        status: "clarification",
        knowledge: { ...ownerKnowledge, reason_code: "ambiguous_subject" },
        subject_candidates: [shipmentSubject],
      }}
      onChooseSubject={choose}
    />,
  );
  const candidate = screen.getByRole("button", {
    name: /出货额 Metric Catalog asset/,
  });
  const enter = createEvent.keyDown(candidate, {
    key: "Enter",
    isComposing: true,
    cancelable: true,
  });
  fireEvent(candidate, enter);
  expect(enter.defaultPrevented).toBe(true);
  fireEvent.compositionStart(candidate);
  await user.click(candidate);
  expect(choose).not.toHaveBeenCalled();
  fireEvent.compositionEnd(candidate);
  await user.click(candidate);
  expect(choose).toHaveBeenCalledExactlyOnceWith(shipmentSubject);
});

it("renders a no-knowledge refusal without misleading metric suggestions or actions", () => {
  render(
    <AskAnswerView
      answer={{
        ...knowledgeAnswer,
        status: "unanswerable",
        message: "warranties is registered, but no ownership is recorded.",
        knowledge: {
          ...ownerKnowledge,
          reason_code: "no_knowledge",
          system_records: [],
          claims: [],
          pending_ambiguous_links: 0,
        },
      }}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("heading", {
      name: "No knowledge can answer this question",
    }),
  ).toBeVisible();
  expect(
    screen.getByText(
      "The subject is registered, but neither system records nor documents answer this question.",
    ),
  ).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "Related subjects" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", {
      name: "Ask the metric owner to add a definition",
    }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});

it.each(["unanswerable", "clarification"] as const)(
  "shows pending links for a knowledge %s without claiming that records do not exist",
  (status) => {
    render(
      <AskAnswerView
        answer={{
          ...knowledgeAnswer,
          status,
          knowledge: {
            ...ownerKnowledge,
            reason_code:
              status === "unanswerable" ? "pending_links" : "ambiguous_subject",
            system_records: [],
            claims: [],
            pending_ambiguous_links: 2,
          },
        }}
        onOpenReceipt={vi.fn()}
      />,
    );
    expect(
      screen.getByText(
        "2 document claims have ambiguous asset links awaiting confirmation.",
      ),
    ).toBeVisible();
    expect(
      screen.queryByText(
        "The subject is registered, but neither system records nor documents answer this question.",
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Calculated result"),
    ).not.toBeInTheDocument();
  },
);

it("explains unsupported knowledge phrasing without claiming the subject is unknown", () => {
  render(
    <KnowledgeResolution
      answer={{
        ...knowledgeAnswer,
        status: "unanswerable",
        knowledge: {
          ...ownerKnowledge,
          reason_code: "unsupported_phrasing",
          pending_ambiguous_links: 0,
        },
      }}
    />,
  );
  expect(
    screen.getByText(
      "This knowledge question could not be interpreted. Try naming the subject and asking about its owner, upstream, or downstream.",
    ),
  ).toBeVisible();
  expect(
    screen.queryByText(
      "The subject could not be identified. Try one of the related subjects below.",
    ),
  ).not.toBeInTheDocument();
});

it("distinguishes same-name candidates using their source dataset and entity type", async () => {
  const user = userEvent.setup();
  const choose = vi.fn();
  const candidates = ["Operations notes", "Finance notes"].map(
    (dataset, index) => ({
      ...shipmentSubject,
      name: "Morgan",
      kind: "kg_entity" as const,
      entity_type: "person",
      dataset_name: dataset,
      asset_ref: {
        ...shipmentSubject.asset_ref,
        asset_id: `kg-${String(index)}a7c4e9`,
        asset_type: "kg_entity",
      },
    }),
  );
  render(
    <KnowledgeResolution
      answer={{
        ...knowledgeAnswer,
        status: "clarification",
        subject_candidates: candidates,
      }}
      onChooseSubject={choose}
    />,
  );
  for (const candidate of candidates) {
    const button = screen.getByRole("button", {
      name: new RegExp(
        `Morgan Graph entity · person Document entity Dataset: ${candidate.dataset_name}`,
      ),
    });
    expect(within(button).getByText("Graph entity · person")).toBeVisible();
    expect(button).not.toHaveTextContent(candidate.asset_ref.asset_id);
    await user.click(button);
    expect(choose).toHaveBeenLastCalledWith(candidate);
  }
});

it("lists metric, catalog, and graph suggestions for an unknown subject", () => {
  render(
    <KnowledgeResolution
      answer={{
        ...knowledgeAnswer,
        status: "unanswerable",
        knowledge: { ...ownerKnowledge, reason_code: "unknown_subject" },
        subject_candidates: [
          shipmentSubject,
          {
            ...shipmentSubject,
            name: "sales",
            kind: "table",
            asset_ref: {
              ...shipmentSubject.asset_ref,
              asset_id: "crm/main/sales",
              asset_type: "table",
            },
          },
          {
            ...shipmentSubject,
            name: "Priya",
            kind: "kg_entity",
            entity_type: "person",
            asset_ref: {
              ...shipmentSubject.asset_ref,
              asset_id: "priya",
              asset_type: "kg_entity",
            },
          },
        ],
      }}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Related subjects" }),
  ).toBeVisible();
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByText("Table")).toBeVisible();
  expect(screen.getByText("Graph entity · person")).toBeVisible();
});

it("asks for an intent with two choices and protects composition confirmation", async () => {
  const choose = vi.fn();
  const user = userEvent.setup();
  render(
    <AskAnswerView
      answer={{
        ...knowledgeAnswer,
        status: "clarification",
        knowledge: {
          ...ownerKnowledge,
          reason_code: "ambiguous_intent",
          intent_candidates: ["upstream", "downstream"],
        },
      }}
      onChooseIntent={choose}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Choose what you want to know" }),
  ).toBeVisible();
  expect(
    screen.getByText("Choose what you want to know", {
      selector: ".ask-answer-heading .badge",
    }),
  ).toBeVisible();
  expect(
    screen.queryByText("Choose the subject first"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Possible subjects" }),
  ).not.toBeInTheDocument();
  const choices = screen.getByRole("group", {
    name: "Which relationship would you like to ask about?",
  });
  expect(within(choices).getAllByRole("button")).toHaveLength(2);
  const upstream = within(choices).getByRole("button", { name: "Upstream" });
  const enter = createEvent.keyDown(upstream, {
    key: "Enter",
    isComposing: true,
    cancelable: true,
  });
  fireEvent(upstream, enter);
  expect(enter.defaultPrevented).toBe(true);
  fireEvent.compositionStart(upstream);
  await user.click(upstream);
  expect(choose).not.toHaveBeenCalled();
  fireEvent.compositionEnd(upstream);
  await user.click(upstream);
  expect(choose).toHaveBeenCalledExactlyOnceWith("upstream");
});
