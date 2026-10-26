import { render, screen } from "@testing-library/react";
import { assert, expect, it } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { imageRun } from "../../test/kgImageFixtures";

import { KGTranscriptions } from "./KGTranscriptions";

import type { Locale } from "../../i18n/context";

const messages: {
  locale: Locale;
  warning: string;
  ignored: string;
  failure: string;
}[] = [
  {
    locale: "en",
    warning:
      "Model coordinates differ from OCR; boxes discarded. Review locations.",
    ignored: "Ignored extra fields: 2",
    failure: "Could not parse the image transcript. Retry or use OCR.",
  },
  {
    locale: "zh",
    warning: "模型坐标与 OCR 不符，已丢弃图框，需人工复核。",
    ignored: "已忽略额外字段：2",
    failure: "无法解析图片转写结果，请重试或使用 OCR。",
  },
];

it.each(messages)(
  "shows discarded coordinate boxes and ignored fields in $locale",
  ({ locale, warning, ignored }) => {
    const report = imageRun.report;
    assert(report);
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: () => undefined, t: translator(locale) }}
      >
        <KGTranscriptions
          report={{
            ...report,
            transcriptions: [
              {
                ...report.transcriptions[0],
                quality_issues: ["coordinates_unreliable"],
                ignored_field_count: 2,
              },
            ],
          }}
        />
      </I18nContext.Provider>,
    );
    expect(screen.getByText(warning)).toBeVisible();
    expect(screen.getByText(ignored)).toBeVisible();
  },
);

it.each(messages)(
  "explains unparseable structured output in $locale",
  ({ locale, warning, ignored, failure }) => {
    const report = imageRun.report;
    assert(report);
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: () => undefined, t: translator(locale) }}
      >
        <KGTranscriptions
          report={{
            ...report,
            transcriptions: [
              {
                ...report.transcriptions[0],
                status: "failed",
                cached: false,
                quality_issues: ["unparseable_structured_output"],
                ignored_field_count: 0,
                error: "unparseable_structured_output",
              },
            ],
          }}
        />
      </I18nContext.Provider>,
    );
    expect(screen.getByText(failure)).toBeVisible();
    expect(screen.queryByText("unparseable_structured_output")).toBeNull();
    expect(screen.queryByText(warning)).toBeNull();
    expect(screen.queryByText(ignored)).toBeNull();
    expect(
      screen.queryByText(/Ignored extra fields: 0|已忽略额外字段：0/),
    ).toBeNull();
  },
);
