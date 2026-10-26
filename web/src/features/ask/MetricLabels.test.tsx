import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { AskAnswerView } from "./AskAnswerView";
import { AskHistory } from "./AskHistory";
import { AskResolution } from "./AskResolution";
import { MetricEvidence } from "./MetricEvidence";
import { retailAnswer, retailMetric, unavailableAnswer } from "./testFixtures";

import type { AskMetric } from "../../api/ask";
import type { Locale } from "../../i18n/context";
import type { ReactNode } from "react";

const metric: AskMetric = {
  ...retailMetric,
  owner_english_name: "Custom metric owner",
  definition: {
    ...retailMetric.definition,
    name: "自定义营收",
    english_name: "Custom turnover",
    owner: "自定义负责人",
  },
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

it.each(["en", "zh"] as const)(
  "uses the frozen metric label above the unchanged numeric answer in %s",
  (locale) => {
    const { container } = localized(
      locale,
      <AskAnswerView
        answer={{ ...retailAnswer, metric_card: metric }}
        onOpenReceipt={vi.fn()}
      />,
    );
    expect(container.querySelector(".ask-result .eyebrow")).toHaveTextContent(
      locale === "en" ? "Custom turnover" : "自定义营收",
    );
    expect(container.querySelector(".ask-scalar")).toHaveTextContent(
      "4,979,475",
    );
    expect(metric.definition.name).toBe("自定义营收");
  },
);

it.each([
  ["en", "clarification"],
  ["zh", "clarification"],
  ["en", "unanswerable"],
  ["zh", "unanswerable"],
] as const)(
  "localizes candidate labels in %s for %s while selecting the original ID",
  async (locale, status) => {
    const selected = vi.fn();
    const { container } = localized(
      locale,
      <AskResolution
        answer={{ ...unavailableAnswer, status, candidates: [metric] }}
        onChooseMetric={selected}
      />,
    );
    const name = locale === "en" ? "Custom turnover" : "自定义营收";
    const owner = locale === "en" ? "Custom metric owner" : "自定义负责人";
    expect(container.querySelector("li")).toHaveTextContent(owner);
    if (status === "clarification") {
      await userEvent.click(
        screen.getByRole("button", { name: new RegExp(name) }),
      );
      expect(selected).toHaveBeenCalledExactlyOnceWith(metric.definition.id);
    } else {
      expect(screen.getByRole("link", { name })).toHaveAttribute(
        "href",
        `#/object/metric/${metric.definition.id}?tab=relations`,
      );
    }
  },
);

it.each(["en", "zh"] as const)(
  "localizes the metric evidence name and owner in %s without changing its formula",
  (locale) => {
    const { container } = localized(locale, <MetricEvidence metric={metric} />);
    expect(
      screen.getByRole("heading", {
        name: locale === "en" ? "Custom turnover" : "自定义营收",
      }),
    ).toBeVisible();
    expect(container.querySelector(".ask-facts dd")).toHaveTextContent(
      locale === "en" ? "Custom metric owner" : "自定义负责人",
    );
    expect(screen.getByText("sum(ecommerce/main/orders/amount)")).toBeVisible();
    expect(metric.definition.owner).toBe("自定义负责人");
  },
);

it.each(["en", "zh"] as const)(
  "localizes the saved-answer label in %s and replays the unchanged answer ID",
  async (locale) => {
    const replay = vi.fn();
    const { container } = localized(
      locale,
      <AskHistory
        answers={[{ ...retailAnswer, metric_card: metric }]}
        onReplay={replay}
      />,
    );
    expect(container.querySelector(".ask-replay p")).toHaveTextContent(
      locale === "en" ? "Custom turnover" : "自定义营收",
    );
    expect(screen.getByText(retailAnswer.question)).toBeVisible();
    await userEvent.click(screen.getByRole("button"));
    expect(replay).toHaveBeenCalledExactlyOnceWith(retailAnswer.id);
  },
);

it.each(["answer", "candidate", "evidence", "history"] as const)(
  "keeps the original %s label when frozen metadata has no English name",
  (surface) => {
    const legacy = {
      ...metric,
      owner_english_name: undefined,
      definition: { ...metric.definition, english_name: undefined },
    };
    const answer = { ...retailAnswer, metric_card: legacy };
    const views = {
      answer: <AskAnswerView answer={answer} onOpenReceipt={vi.fn()} />,
      candidate: (
        <AskResolution
          answer={{ ...unavailableAnswer, candidates: [legacy] }}
        />
      ),
      evidence: <MetricEvidence metric={legacy} />,
      history: <AskHistory answers={[answer]} onReplay={vi.fn()} />,
    };
    const { container } = localized("en", views[surface]);
    expect(container).toHaveTextContent("自定义营收");
    if (surface === "candidate" || surface === "evidence")
      expect(container).toHaveTextContent("自定义负责人");
  },
);
