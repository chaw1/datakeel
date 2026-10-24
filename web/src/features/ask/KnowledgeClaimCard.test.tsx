import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";

import { KnowledgeAnswerView } from "./KnowledgeAnswerView";
import { KnowledgeClaimCard } from "./KnowledgeClaimCard";
import {
  claimExplanation,
  ownerClaim,
  ownerKnowledge,
} from "./knowledgeFixtures";

it.each([
  ["en", "owns", "owns"],
  ["en", "computed_from", "computed from"],
  ["en", "derived_from", "derived from"],
  ["zh", "owns", "负责"],
  ["zh", "computed_from", "基于…计算"],
  ["zh", "derived_from", "由…加工"],
])("localizes the %s relation %s", (locale, predicate, label) => {
  localStorage.setItem("datakeel.locale", locale);
  render(
    <I18nProvider>
      <KnowledgeClaimCard
        claim={{ ...ownerClaim, predicate }}
        onInspect={vi.fn()}
      />
    </I18nProvider>,
  );
  expect(
    screen.getByRole("button", { name: `周岩 ${label} 出货额` }),
  ).toBeVisible();
});

it("retains the original predicate in the source drawer for a localized relation", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            ...claimExplanation,
            relation: {
              ...claimExplanation.relation,
              assertion: {
                ...claimExplanation.relation.assertion,
                predicate: "kg.computed_from",
              },
            },
          }),
        ),
      ),
    ),
  );
  render(
    <KnowledgeAnswerView
      knowledge={{
        ...ownerKnowledge,
        claims: [{ ...ownerClaim, predicate: "computed_from" }],
      }}
    />,
  );
  expect(screen.queryByText("computed_from")).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: "周岩 computed from 出货额" }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Relation source evidence",
  });
  expect(await within(dialog).findByText("kg.computed_from")).toBeVisible();
});
