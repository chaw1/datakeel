import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import {
  knowledgeAnswer,
  ownerKnowledge,
  shipmentSubject,
} from "../features/ask/knowledgeFixtures";

import { AskPage } from "./AskPage";

const otherSubject = {
  ...shipmentSubject,
  name: "零售额",
  asset_ref: { ...shipmentSubject.asset_ref, asset_id: "retail_revenue" },
};

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

it("repeats the saved question with the selected intent and subject", async () => {
  const question = "出货额与哪些指标有关";
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...knowledgeAnswer,
          question,
          status: "clarification",
          knowledge: {
            ...ownerKnowledge,
            reason_code: "ambiguous_intent",
            intent_candidates: ["upstream", "downstream"],
          },
        }),
      ),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(knowledgeAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  const input = screen.getByRole("textbox", { name: "Business question" });
  await user.type(input, question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  const downstream = await screen.findByRole("button", { name: "Downstream" });
  await user.clear(input);
  await user.type(input, "An unrelated edited question");
  await user.click(downstream);
  expect(
    await screen.findByRole("region", { name: "System records" }),
  ).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        question,
        reference_instant: knowledgeAnswer.reference_instant,
        session_id: knowledgeAnswer.session_id,
        subject_id: shipmentSubject.asset_ref.asset_id,
        knowledge_intent: "downstream",
      }),
    }),
  );
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});

it("retains a selected intent when a later response asks to choose the subject", async () => {
  const question = "出货额与哪些指标有关";
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...knowledgeAnswer,
          question,
          status: "clarification",
          knowledge: {
            ...ownerKnowledge,
            subject: null,
            reason_code: "ambiguous_intent",
            intent_candidates: ["upstream", "downstream"],
          },
        }),
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...knowledgeAnswer,
          question,
          status: "clarification",
          knowledge: {
            ...ownerKnowledge,
            subject: null,
            reason_code: "ambiguous_subject",
          },
          subject_candidates: [shipmentSubject],
        }),
      ),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(knowledgeAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.type(screen.getByRole("textbox"), question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await user.click(await screen.findByRole("button", { name: "Upstream" }));
  await user.click(
    await screen.findByRole("button", { name: /出货额 Metric Catalog asset/ }),
  );
  expect(
    await screen.findByRole("region", { name: "System records" }),
  ).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        question,
        reference_instant: knowledgeAnswer.reference_instant,
        session_id: knowledgeAnswer.session_id,
        subject_id: shipmentSubject.asset_ref.asset_id,
        knowledge_intent: "upstream",
      }),
    }),
  );
});

it("restores a selected intent from a replayed subject clarification", async () => {
  const clarification = {
    ...knowledgeAnswer,
    status: "clarification",
    knowledge: {
      ...ownerKnowledge,
      subject: null,
      intent: "upstream",
      reason_code: "ambiguous_subject",
    },
    subject_candidates: [shipmentSubject, otherSubject],
  };
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(clarification)))
    .mockResolvedValueOnce(new Response(JSON.stringify(clarification)))
    .mockResolvedValueOnce(new Response(JSON.stringify(knowledgeAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.type(screen.getByRole("textbox"), knowledgeAnswer.question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await user.click(
    await screen.findByRole("button", { name: "Replay saved answer" }),
  );
  await user.click(
    await screen.findByRole("button", { name: /出货额 Metric Catalog asset/ }),
  );
  expect(
    await screen.findByRole("region", { name: "System records" }),
  ).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        question: knowledgeAnswer.question,
        reference_instant: knowledgeAnswer.reference_instant,
        session_id: knowledgeAnswer.session_id,
        subject_id: shipmentSubject.asset_ref.asset_id,
        knowledge_intent: "upstream",
      }),
    }),
  );
});

it("keeps the pinned subject when a subject choice is followed by an intent choice", async () => {
  const question = "营业额有哪些关联";
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...knowledgeAnswer,
          question,
          status: "clarification",
          knowledge: {
            ...ownerKnowledge,
            subject: null,
            reason_code: "ambiguous_subject",
          },
          subject_candidates: [shipmentSubject, otherSubject],
        }),
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...knowledgeAnswer,
          question,
          status: "clarification",
          knowledge: {
            ...ownerKnowledge,
            reason_code: "ambiguous_intent",
            intent_candidates: ["upstream", "downstream", "owner"],
          },
        }),
      ),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(knowledgeAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.type(screen.getByRole("textbox"), question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await user.click(
    await screen.findByRole("button", { name: /出货额 Metric Catalog asset/ }),
  );
  await user.click(await screen.findByRole("button", { name: "Downstream" }));
  expect(
    await screen.findByRole("region", { name: "System records" }),
  ).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        question,
        reference_instant: knowledgeAnswer.reference_instant,
        session_id: knowledgeAnswer.session_id,
        subject_id: shipmentSubject.asset_ref.asset_id,
        knowledge_intent: "downstream",
      }),
    }),
  );
});
