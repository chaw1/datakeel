import { createEvent, fireEvent, render, screen } from "@testing-library/react";
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
    name: /出货额 Metric shipment_revenue/,
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
