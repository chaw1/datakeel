import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";

import { AskAnswerView } from "./AskAnswerView";
import { KnowledgeAnswerView } from "./KnowledgeAnswerView";
import { KnowledgeClaimCard } from "./KnowledgeClaimCard";
import {
  claimExplanation,
  knowledgeAnswer,
  ownerClaim,
  ownerKnowledge,
} from "./knowledgeFixtures";
import { retailAnswer } from "./testFixtures";

it("separates registered roles from source claims, review status and pending ambiguous links", () => {
  render(<AskAnswerView answer={knowledgeAnswer} onOpenReceipt={vi.fn()} />);
  expect(
    within(screen.getByRole("region", { name: "System records" })).getByText(
      "供应链负责人",
    ),
  ).toBeVisible();
  const documents = screen.getByRole("region", { name: "Document claims" });
  expect(
    within(documents).getByRole("button", { name: "周岩 owns 出货额" }),
  ).toBeVisible();
  expect(within(documents).getByText("Awaiting confirmation")).toBeVisible();
  expect(within(documents).getByText("Verified")).toBeVisible();
  expect(within(documents).getByText("周岩负责出货额。")).toBeVisible();
  expect(within(documents).getByText("Source: handoff.txt")).toBeVisible();
  expect(
    within(documents).getByText("Asset link awaiting confirmation"),
  ).toBeVisible();
  expect(
    within(documents).getByText(
      "1 document claims have ambiguous asset links awaiting confirmation.",
    ),
  ).toBeVisible();
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
  expect(
    screen.queryByText("No rows matched this question."),
  ).not.toBeInTheDocument();
});

it("opens and closes the existing source relation drawer from a document claim", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(claimExplanation))),
  );
  vi.stubGlobal("fetch", fetch);
  render(<KnowledgeAnswerView knowledge={ownerKnowledge} />);
  await user.click(screen.getByRole("button", { name: "周岩 owns 出货额" }));
  const dialog = await screen.findByRole("dialog", {
    name: "Relation source evidence",
  });
  expect(await within(dialog).findByText("handoff.txt")).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/kg/relations/claim-owner",
    expect.anything(),
  );
  await user.click(
    within(dialog).getByRole("button", { name: "Close graph details" }),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "周岩 owns 出货额" }),
  ).toHaveFocus();
});

it.each([
  ["consistent", "Consistent with the system"],
  ["not_in_system", "Not in system records"],
  ["not_in_catalog", "Not in the catalog"],
] as const)(
  "renders %s independently of accepted and needs-review statuses",
  (consistency, label) => {
    render(
      <KnowledgeClaimCard
        claim={{
          ...ownerClaim,
          relation_status: "accepted",
          verification: "needs_review",
          consistency,
          subject_link: {
            entity: ownerClaim.tail,
            asset_ref: ownerClaim.tail.asset_ref,
            assertion_id: "subject-link",
            link_status: "accepted",
          },
        }}
        onInspect={vi.fn()}
      />,
    );
    expect(screen.getByText(label)).toBeVisible();
    expect(screen.getByText("Confirmed")).toBeVisible();
    expect(screen.getByText("Needs review")).toBeVisible();
    expect(screen.getByText("Asset link confirmed")).toBeVisible();
  },
);

it("shows the linked other endpoint and its independent pending link status", () => {
  render(
    <KnowledgeClaimCard
      claim={{
        ...ownerClaim,
        subject_link: null,
        other_end: {
          status: "linked",
          entity: ownerClaim.tail,
          asset_ref: {
            ...ownerClaim.tail.asset_ref,
            asset_type: "metric",
            asset_id: "shipment_revenue",
          },
          assertion_id: "other-link",
          link_status: "candidate",
        },
      }}
      onInspect={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("link", { name: "shipment_revenue" }),
  ).toHaveAttribute("href", "#/object/metric/shipment_revenue?tab=relations");
  expect(screen.getByText("Asset link awaiting confirmation")).toBeVisible();
});

it("keeps the metric result unchanged when related knowledge is attached", () => {
  render(
    <AskAnswerView
      answer={{
        ...retailAnswer,
        knowledge: { ...ownerKnowledge, intent: "related" },
      }}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Calculated result")).toHaveTextContent(
    "4,979,475",
  );
  expect(
    screen.getByRole("heading", { name: "Related knowledge" }),
  ).toBeVisible();
  expect(screen.getByText("Source: handoff.txt")).toBeVisible();
  expect(
    screen.queryByRole("region", { name: "System records" }),
  ).not.toBeInTheDocument();
});

it("renders empty system/document states and Chinese knowledge labels", () => {
  localStorage.setItem("datakeel.locale", "zh");
  render(
    <I18nProvider>
      <KnowledgeAnswerView
        knowledge={{
          ...ownerKnowledge,
          system_records: [],
          claims: [],
          pending_ambiguous_links: 0,
        }}
      />
    </I18nProvider>,
  );
  expect(screen.getByRole("region", { name: "系统记录" })).toBeVisible();
  expect(screen.getByText("系统里没有登记负责人。")).toBeVisible();
  expect(screen.getByRole("region", { name: "文档里的说法" })).toBeVisible();
  expect(screen.getByText("没有符合本题的文档说法。")).toBeVisible();
  expect(screen.queryByText(/还有/)).not.toBeInTheDocument();
});
