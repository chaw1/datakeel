import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { display } from "../../lib/format";

import { Paragraphs } from "./Paragraphs";

import type { Report } from "../../api/types";
export function ReportView({
  report,
  context = "dataset",
}: {
  report: Report | null;
  context?: "dataset" | "standards";
}) {
  const { t } = useI18n();

  if (!report)
    return (
      <div className="empty-state">
        <Icon name="report" size={28} />
        <h3>{t("yourReportIsBeingPrepared")}</h3>
        <p>{t("theBaselineReportWillAppearAfterAnalysisCompletes")}</p>
      </div>
    );
  const chapters = report.chapters;
  return (
    <div className="report-layout">
      <aside className="report-index">
        <span className="eyebrow">{t("inThisReport")}</span>
        {chapters.map((chapter, index) => (
          <a href={`#chapter-${String(index)}`} key={index}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            {chapter.title}
          </a>
        ))}
      </aside>
      <div className="report-body">
        <div className="report-cover">
          <span className="eyebrow">
            {t(context === "standards" ? "stdNav" : "datasetIntelligence")}
          </span>
          <h2>
            {context === "standards" ? (
              t("stdAnalysis")
            ) : (
              <>
                {t("fromRawData")} <br />
                {t("toInformedDecisions")}
              </>
            )}
          </h2>
          <p>
            {t(
              context === "standards"
                ? "stdIntro"
                : "aPracticalAssessmentOfQualitySuitabilityAndTheNextStepsForYourDataset",
            )}{" "}
          </p>
          <span className="badge green">
            <Icon name="check" size={13} />
            {t("baselineVerified")}{" "}
          </span>
          {report.fallback && (
            <span className="badge amber">{t("baselineFallback")}</span>
          )}
        </div>
        {chapters.map((chapter, index) => (
          <section
            id={`chapter-${String(index)}`}
            className="report-chapter"
            key={index}
          >
            <span className="chapter-number">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div>
              <h3>{chapter.title}</h3>
              <Paragraphs body={chapter.body} />
            </div>
          </section>
        ))}
        {report.body && (!chapters.length || Boolean(report.llm_body)) && (
          <section className="report-chapter">
            <div>
              <h3>{t("analysis")}</h3>
              <Paragraphs body={display(report.llm_body || report.body, "")} />
            </div>
          </section>
        )}
        {report.baseline_verification ? (
          <p className="baseline-note">
            {display(report.baseline_verification)}
          </p>
        ) : null}
        {report.fallback && (
          <p className="fallback-note">
            {t(
              "theConfiguredLanguageServiceWasUnavailableThisReportUsesTheCompleteRuleBasedBaseline",
            )}{" "}
          </p>
        )}
      </div>
    </div>
  );
}
