import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";

import { AskAnswerView } from "./AskAnswerView";
import {
  knowledgeAnswer,
  ownerKnowledge,
  shipmentSubject,
} from "./knowledgeFixtures";
import { QuestionEvidence } from "./QuestionEvidence";

it.each([
  [
    "en",
    "Matched question text",
    "Subject “出货额” matches Metric Shipment revenue.",
    "Asked for “哪份数据” (table or view) → Upstream",
    "Direction: Upstream; evidence: “依赖”",
    "Recognition rule: K-03",
  ],
  [
    "zh",
    "问题中的匹配证据",
    "主语『出货额』匹配到指标 出货额。",
    "问的是『哪份数据』（表或视图） → 上游",
    "方向：上游；依据：『依赖』",
    "识别规则：K-03",
  ],
])(
  "explains subject, focus, direction, and rule in %s",
  (locale, heading, subject, focus, direction, rule) => {
    localStorage.setItem("datakeel.locale", locale);
    render(
      <I18nProvider>
        <AskAnswerView
          answer={{
            ...knowledgeAnswer,
            question: "出货额依赖哪份数据",
            knowledge: { ...ownerKnowledge, intent: "upstream" },
            recognition: {
              subjects: [
                {
                  text: "出货额",
                  subject: {
                    ...shipmentSubject,
                    english_name: "Shipment revenue",
                  },
                },
              ],
              focus: "table",
              focus_text: "哪份数据",
              direction: "upstream",
              direction_text: ["依赖"],
              rule_id: "K-03",
            },
          }}
          onOpenReceipt={vi.fn()}
        />
      </I18nProvider>,
    );
    const evidence = screen.getByRole("region", { name: heading });
    for (const text of [subject, focus, direction, rule])
      expect(within(evidence).getByText(text)).toBeVisible();
    expect(screen.queryByText("shipment_revenue")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Calculated result"),
    ).not.toBeInTheDocument();
  },
);

it("explains an unknown subject without claiming a type or direction was recognized", () => {
  render(
    <QuestionEvidence
      question="Where does an unregistered report come from?"
      matches={[]}
      recognition={{
        rule_id: "K-unknown",
        subjects: [],
        focus: "location",
        focus_text: "Where",
        direction: null,
        direction_text: [],
      }}
    />,
  );
  expect(
    screen.getByText("No registered subject matched the question."),
  ).toBeVisible();
  expect(
    screen.getByText("Asked for “Where” (source or location)"),
  ).toBeVisible();
  expect(screen.getByText("Recognition rule: K-unknown")).toBeVisible();
  expect(screen.queryByText(/Direction:/)).not.toBeInTheDocument();
  expect(
    screen.queryByText("No registered terms matched the question."),
  ).not.toBeInTheDocument();
});

it.each([
  ["metric", "未登记英文名的指标", "Metric 未登记英文名的指标"],
  ["kg_entity", "华东仓", "Graph entity 华东仓"],
] as const)(
  "keeps a %s subject's own name in English when it has no English name",
  (kind, name, shown) => {
    localStorage.setItem("datakeel.locale", "en");
    render(
      <I18nProvider>
        <QuestionEvidence
          question={name}
          matches={[]}
          recognition={{
            rule_id: "K-01",
            subjects: [
              { text: name, subject: { ...shipmentSubject, kind, name } },
            ],
            focus: "unknown",
            focus_text: "",
            direction: null,
            direction_text: [],
          }}
        />
      </I18nProvider>,
    );
    expect(
      screen.getByText(`Subject “${name}” matches ${shown}.`),
    ).toBeVisible();
  },
);
