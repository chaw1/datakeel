import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { AskAnswerView } from "./AskAnswerView";
import { AskHistory } from "./AskHistory";
import { KnowledgeAnswerView } from "./KnowledgeAnswerView";
import { ownerKnowledge, shipmentSubject } from "./knowledgeFixtures";
import { retailAnswer } from "./testFixtures";

import type { Locale } from "../../i18n/context";
import type { ReactNode } from "react";

const CHINESE = /[一-鿿]/;
const answer = {
  ...retailAnswer,
  question: "上个季度华东零售额",
  interpreted_question: "查询零售额,时间从2026-07-01至2026-10-01(不含结束日)。",
  interpreted_question_en:
    "Query Retail revenue, from 2026-07-01 to 2026-10-01 (end date excluded).",
};

function localized(locale: Locale, children: ReactNode) {
  return render(
    <I18nContext.Provider
      value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
    >
      {children}
    </I18nContext.Provider>,
  );
}

it.each([
  ["en", answer.interpreted_question_en],
  ["zh", answer.interpreted_question],
] as const)(
  "shows how the question was understood in the %s interface's language",
  (locale, understood) => {
    const { container } = localized(
      locale,
      <>
        <AskAnswerView answer={answer} onOpenReceipt={vi.fn()} />
        <AskHistory answers={[answer]} onReplay={vi.fn()} />
      </>,
    );
    expect(container.querySelector(".ask-understood")).toHaveTextContent(
      understood,
    );
    expect(
      container.querySelector(".ask-replay")?.textContent.includes(understood),
    ).toBe(true);
  },
);

it("falls back to the question as asked, not the Chinese wording, for older answers", () => {
  const { container } = localized(
    "en",
    <AskAnswerView
      answer={{ ...answer, interpreted_question_en: "" }}
      onOpenReceipt={vi.fn()}
    />,
  );
  const understood = container.querySelector(".ask-understood");
  expect(understood).toHaveTextContent(answer.question);
  expect(understood).not.toHaveTextContent("查询零售额");
});

it.each([
  ["en", "Shipment revenue"],
  ["zh", "出货额"],
] as const)(
  "names the knowledge subject by its registered %s name",
  (locale, heading) => {
    localized(
      locale,
      <KnowledgeAnswerView
        knowledge={{
          ...ownerKnowledge,
          subject: { ...shipmentSubject, english_name: "Shipment revenue" },
        }}
      />,
    );
    const title = screen.getByRole("heading", { level: 2 });
    expect(title).toHaveTextContent(heading);
    expect(CHINESE.test(title.textContent)).toBe(locale === "zh");
  },
);
