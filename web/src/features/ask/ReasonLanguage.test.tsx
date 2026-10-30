import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { AskChart } from "./AskChart";
import { AskResolution } from "./AskResolution";
import {
  knowledgeAnswer,
  ownerKnowledge,
  shipmentSubject,
} from "./knowledgeFixtures";
import { KnowledgeResolution } from "./KnowledgeResolution";
import { ProfileAnswerView } from "./ProfileAnswerView";
import { retailAnswer, unavailableAnswer } from "./testFixtures";

import type { AskAnswer } from "../../api/ask";
import type { Locale } from "../../i18n/context";
import type { ReactNode } from "react";

const CHINESE_TEMPLATE = /登记|解析|维度|无法|请明确|未理解/;

function localized(locale: Locale, children: ReactNode) {
  return render(
    <I18nContext.Provider
      value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
    >
      {children}
    </I18nContext.Provider>,
  );
}

function refusal(reason: AskAnswer["reason"], message: string): AskAnswer {
  return { ...unavailableAnswer, status: "unanswerable", reason, message };
}

function detail(container: HTMLElement) {
  return container.querySelector(".ask-detail p")?.textContent;
}

it.each([
  [
    { code: "unsupported_calculation", fragments: ["中位数"], notes: [] },
    "登记指标不支持所问的计算: 「中位数」",
    "The registered metric does not support the requested calculation: “中位数”.",
  ],
  [
    { code: "time_not_understood", fragments: ["上个世纪"], notes: [] },
    "无法可靠解析时间条件: 未理解「上个世纪」",
    "The time condition could not be read reliably: “上个世纪” was not understood.",
  ],
  [
    {
      code: "unclear_condition",
      fragments: ["上海"],
      notes: ["Region value is not registered for this metric"],
    },
    "请明确维度条件: Region value is not registered for this metric; 未理解「上海」",
    "Clarify the dimension conditions: Region value is not registered for this metric; “上海” was not understood",
  ],
  [
    { code: "execution_failed", fragments: [], notes: ["ExecutionError"] },
    "已登记指标暂时无法执行 (ExecutionError)。",
    "The registered metric could not run just now (ExecutionError).",
  ],
] as const)(
  "words the recorded reason %# in the interface language",
  (reason, chinese, english) => {
    const answer = refusal(
      { ...reason, fragments: [...reason.fragments], notes: [...reason.notes] },
      chinese,
    );
    const en = localized("en", <AskResolution answer={answer} />);
    expect(detail(en.container)).toBe(english);
    expect(detail(en.container)).not.toMatch(CHINESE_TEMPLATE);
    en.unmount();
    const zh = localized("zh", <AskResolution answer={answer} />);
    // The Chinese wording rebuilt from the code is exactly what the server stored.
    expect(detail(zh.container)).toBe(chinese);
  },
);

it("shows a reason recorded before reasons had codes exactly as stored", () => {
  const stored = "登记指标不支持所问的计算: 「中位数」";
  const { container } = localized(
    "en",
    <AskResolution answer={refusal(null, stored)} />,
  );
  expect(detail(container)).toBe(stored);
});

it("words knowledge and profile refusals in the interface language", () => {
  const knowledge: AskAnswer = {
    ...knowledgeAnswer,
    status: "unanswerable",
    message: "出货额 在目录里, 但系统和文档都没有登记本题所需的记录。",
    knowledge: {
      ...ownerKnowledge,
      reason_code: "no_knowledge",
      pending_ambiguous_links: 0,
      subject: { ...shipmentSubject, english_name: "Shipment revenue" },
    },
  };
  const en = localized("en", <KnowledgeResolution answer={knowledge} />);
  expect(detail(en.container)).toBe(
    "Shipment revenue is in the catalog, but neither the system nor any document records what this question needs.",
  );
  en.unmount();
  const profile: AskAnswer = {
    ...unavailableAnswer,
    answer_kind: "profile",
    question: "哪个设备温度缺得最多",
    message: "没有已发布的时序剖析元数据。",
    profile: {
      intent: "device_gaps",
      scope: "sampling_time_axis",
      sort_by: "gap_count",
      candidates: [],
      ranking: [],
      reason_code: "no_profile",
    },
  };
  localized("en", <ProfileAnswerView answer={profile} />);
  expect(
    screen.getByText("No published time-series profile is available."),
  ).toBeVisible();
});

it("captions the chart with the metric name in the interface language", () => {
  const result = {
    columns: ["value"],
    rows: [[4979475]],
    truncated: false,
  };
  const chart = {
    type: "scalar" as const,
    title: "零售额",
    description: "零售额: 1 result rows; value",
    x: null,
    y: ["value"],
    series: null,
    unit: "CNY",
    number_format: "number" as const,
    sort: "source" as const,
    available_types: ["scalar" as const, "table" as const],
    show_percent: false,
  };
  const answer = { ...retailAnswer, result };
  const en = localized(
    "en",
    <AskChart answer={answer} chart={chart} footnotes={[]} />,
  );
  const section = en.container.querySelector(".ask-chart");
  expect(section?.getAttribute("aria-label")).toBe("Retail revenue");
  expect(section?.textContent).toContain(
    "Retail revenue: 1 result rows; value",
  );
  expect(section?.textContent).not.toContain("零售额");
  en.unmount();
  const zh = localized(
    "zh",
    <AskChart answer={answer} chart={chart} footnotes={[]} />,
  );
  expect(
    zh.container.querySelector(".ask-chart")?.getAttribute("aria-label"),
  ).toBe("零售额");
});
