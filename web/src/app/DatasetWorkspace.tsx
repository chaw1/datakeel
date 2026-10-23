import { Icon } from "../components/Icon";
import { useI18n } from "../i18n/useI18n";
import { FilesPage } from "../pages/FilesPage";
import { LineagePage } from "../pages/LineagePage";
import { OverviewPage } from "../pages/OverviewPage";
import { QualityPage } from "../pages/QualityPage";
import { ReportPage } from "../pages/ReportPage";
import { TasksPage } from "../pages/TasksPage";
import { VersionsPage } from "../pages/VersionsPage";

import { tabs } from "./navigation";

import type { Page, LineageTarget } from "./navigation";
import type { Dataset, DatasetData } from "../api/types";
export function DatasetWorkspace({
  data,
  datasets,
  selected,
  selectedId,
  page,
  navigate,
  setSelectedId,
  setRefresh,
  lineageFocus,
}: {
  data: DatasetData;
  datasets: Dataset[];
  selected?: Dataset;
  selectedId: string;
  page: Page;
  lineageFocus?: LineageTarget;
  navigate: (page: Page) => void;
  setSelectedId: (id: string) => void;
  setRefresh: React.Dispatch<React.SetStateAction<number>>;
}) {
  const { t } = useI18n();

  const files = selected?.file_count ?? data.files.length;
  const modalities = [
    ...new Set(data.files.map((file) => file.modality).filter(Boolean)),
  ];
  const completed = data.tasks.filter(
    (task) => task.state.toUpperCase() === "COMPLETED",
  ).length;
  const running = data.tasks.some((task) =>
    ["RUNNING", "PENDING", "QUEUED"].includes(task.state.toUpperCase()),
  );
  return (
    <>
      <div className="page-heading dataset-heading">
        <div>
          <button
            className="back-link"
            onClick={() => {
              navigate("datasets");
            }}
          >
            {t("dataLibrary")}{" "}
          </button>
          <h1>
            {page === "tasks"
              ? t("pipelineRuns")
              : selected?.name || t("datasetWorkspace")}
          </h1>
          <p>
            {page === "tasks"
              ? t("followEveryRunFromTheFirstShardToTheFinalArtifact")
              : t("datasetSummary", {
                  files: files.toLocaleString(),
                  modalities: modalities.length
                    ? modalities.join(" + ")
                    : t("multimodalData"),
                  versions: data.versions.length,
                })}
          </p>
        </div>
        {selected && (
          <div className="export-actions">
            <button
              className="button"
              aria-label={t("refreshDataset")}
              onClick={() => {
                setRefresh((value) => value + 1);
              }}
            >
              <Icon name="refresh" size={15} />
            </button>
            <a
              className="button"
              href={`/api/export?format=openlineage&dataset_id=${encodeURIComponent(selectedId)}`}
              download
            >
              <Icon name="download" size={15} />
              {t("openlineage")}{" "}
            </a>
            <a
              className="button"
              href={`/api/export?format=croissant&dataset_id=${encodeURIComponent(selectedId)}`}
              download
            >
              <Icon name="download" size={15} />
              {t("croissant")}{" "}
            </a>
          </div>
        )}
      </div>
      {datasets.length > 1 && (
        <label className="dataset-selector">
          {t("dataset")}{" "}
          <select
            aria-label={t("selectDataset")}
            value={selectedId}
            onBlur={(event) => {
              setSelectedId(event.target.value);
            }}
            onChange={(event) => {
              setSelectedId(event.target.value);
            }}
          >
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {data.errors.length > 0 && (
        <div className="warning-banner" role="status">
          <strong>{t("someDataIsNotAvailableYet")}</strong>{" "}
          {data.errors.join(" · ")}
        </div>
      )}
      {!selected ? (
        <div className="card empty-state">
          <h3>{t("noDatasetSelected")}</h3>
          <p>{t("yourDataWillAppearHereAfterImport")}</p>
        </div>
      ) : page === "tasks" ? (
        <TasksPage data={data} />
      ) : (
        <>
          <nav className="tabs" aria-label={t("datasetViews")}>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                aria-current={page === tab.id ? "page" : undefined}
                className={page === tab.id ? "active" : ""}
                onClick={() => {
                  navigate(tab.id);
                }}
              >
                {t(tab.label)}
                {tab.id === "files" && <span>{files}</span>}
              </button>
            ))}
          </nav>
          {page === "overview" && (
            <OverviewPage
              data={data}
              files={files}
              modalities={modalities}
              completed={completed}
              running={running}
              navigate={navigate}
            />
          )}
          {page === "files" && (
            <FilesPage data={data} selectedId={selectedId} />
          )}
          {page === "versions" && (
            <VersionsPage data={data} selectedId={selectedId} />
          )}
          {page === "lineage" && (
            <LineagePage
              data={data}
              selectedId={selectedId}
              focus={lineageFocus}
            />
          )}
          {page === "quality" && (
            <QualityPage data={data} selectedId={selectedId} />
          )}
          {page === "report" && (
            <ReportPage data={data} selectedId={selectedId} />
          )}
        </>
      )}
    </>
  );
}
