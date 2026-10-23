import { Icon } from "../components/Icon";
import Lineage from "../features/lineage/Lineage";
import { qualityGrade } from "../features/quality/labels";
import { QualityScore } from "../features/quality/QualityScore";
import { Tasks } from "../features/tasks/Tasks";
import { useI18n } from "../i18n/useI18n";

import type { DatasetData } from "../api/types";
import type { Page } from "../app/navigation";
export function OverviewPage({
  data,
  files,
  modalities,
  completed,
  running,
  navigate,
}: {
  data: DatasetData;
  files: number;
  modalities: string[];
  completed: number;
  running: boolean;
  navigate: (page: Page) => void;
}) {
  const { t } = useI18n();
  return (
    <>
      <div className="metric-grid">
        <div className="metric-card">
          <span>
            {t("totalFiles")} <Icon name="file" />
          </span>
          <strong>{files.toLocaleString()}</strong>
          <p>
            {modalities.length}{" "}
            {t("dataModalities", { count: modalities.length })}
          </p>
        </div>
        <div className="metric-card">
          <span>
            {t("qualityScore")} <Icon name="quality" />
          </span>
          <strong>
            {data.quality ? data.quality.total.toFixed(1) : "—"}
            <small>/ 100</small>
          </strong>
          <p className="green-text">
            {qualityGrade(data.quality?.grade, t, "waitingForAnalysis")}
          </p>
        </div>
        <div className="metric-card">
          <span>
            {t("datasetVersions")} <Icon name="layers" />
          </span>
          <strong>{data.versions.length}</strong>
          <p>{t("immutableManifestSnapshots")}</p>
        </div>
        <div className="metric-card">
          <span>
            {t("pipelineRuns")} <Icon name="activity" />
          </span>
          <strong>
            {completed}
            <small>{t("completed")}</small>
          </strong>
          <p>
            {running
              ? t("processingIsInProgress")
              : t("allTransformationsTracked")}
          </p>
        </div>
      </div>
      <div className="overview-columns">
        <section className="card lineage-card">
          <div className="card-heading">
            <div>
              <h2>{t("aTraceableJourney")}</h2>
              <p>{t("fromSourceDataToEveryTransformation")}</p>
            </div>
            <button
              className="text-button"
              onClick={() => {
                navigate("lineage");
              }}
            >
              {t("exploreLineage")} <Icon name="arrow" size={15} />
            </button>
          </div>
          <Lineage graph={data.graph} compact />
        </section>
        <section className="card quality-preview">
          <div className="card-heading">
            <h2>{t("qualityAtAGlance")}</h2>
            <Icon name="quality" />
          </div>
          <QualityScore quality={data.quality} />
          <span className="badge green">
            {qualityGrade(data.quality?.grade, t, "awaitingAnalysis")}
          </span>
          <p>
            {data.quality?.issues.length ?? 0}{" "}
            {t("findingsAcrossFiveDimensions", {
              count: data.quality?.issues.length ?? 0,
            })}{" "}
          </p>
          <button
            className="text-button"
            onClick={() => {
              navigate("quality");
            }}
          >
            {t("seeQualityDetails")} <Icon name="arrow" size={15} />
          </button>
        </section>
      </div>
      <section className="card recent-runs">
        <div className="card-heading">
          <div>
            <h2>{t("recentActivity")}</h2>
            <p>{t("pipelineProgressUpdatedAsItHappens")}</p>
          </div>
          <button
            className="text-button"
            onClick={() => {
              navigate("tasks");
            }}
          >
            {t("allRuns")} <Icon name="arrow" size={15} />
          </button>
        </div>
        <Tasks tasks={data.tasks} compact />
      </section>
      <button
        className="report-callout"
        onClick={() => {
          navigate("report");
        }}
      >
        <span className="report-callout-icon">
          <Icon name="report" size={24} />
        </span>
        <div>
          <h3>{t("turnAnAssessmentIntoYourNextStep")}</h3>
          <p>
            {t(
              "readTheSixPartReportForQualityConclusionsUseCasesAndGovernanceRecommendations",
            )}{" "}
          </p>
        </div>
        <span className="button">
          {t("readReport")} <Icon name="arrow" size={16} />
        </span>
      </button>
    </>
  );
}
