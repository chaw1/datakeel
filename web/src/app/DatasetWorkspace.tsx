import { Icon } from "../components/Icon";
import {
  Button,
  EmptyState,
  PageHeader,
  SegmentedTabs,
  Select,
} from "../components/ui";
import { useI18n } from "../i18n/useI18n";
import { DatasheetsPage } from "../pages/DatasheetsPage";
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
      <PageHeader
        compact
        className="dataset-heading"
        backAction={
          <button
            className="back-link"
            onClick={() => {
              navigate("datasets");
            }}
          >
            {t("dataLibrary")}{" "}
          </button>
        }
        title={
          page === "tasks"
            ? t("pipelineRuns")
            : selected?.name || t("datasetWorkspace")
        }
        subtitle={
          page === "tasks"
            ? t("followEveryRunFromTheFirstShardToTheFinalArtifact")
            : t("datasetSummary", {
                files: files.toLocaleString(),
                modalities: modalities.length
                  ? modalities.join(" + ")
                  : t("multimodalData"),
                versions: data.versions.length,
              })
        }
        actions={
          selected && (
            <div className="export-actions">
              <Button
                icon="refresh"
                iconSize={15}
                aria-label={t("refreshDataset")}
                onClick={() => {
                  setRefresh((value) => value + 1);
                }}
              />
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
          )
        }
      />
      {datasets.length > 1 && (
        <label className="dataset-selector">
          {t("dataset")}{" "}
          <Select
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
          </Select>
        </label>
      )}
      {data.errors.length > 0 && (
        <div className="warning-banner" role="status">
          <strong>{t("someDataIsNotAvailableYet")}</strong>{" "}
          {data.errors.join(" · ")}
        </div>
      )}
      {!selected ? (
        <EmptyState
          card
          title={t("noDatasetSelected")}
          description={t("yourDataWillAppearHereAfterImport")}
        />
      ) : page === "tasks" ? (
        <TasksPage data={data} />
      ) : (
        <>
          <SegmentedTabs
            label={t("datasetViews")}
            activeId={page}
            onSelect={navigate}
            items={tabs.map((tab) => ({
              id: tab.id,
              label: t(tab.label),
              count: tab.id === "files" ? files : undefined,
            }))}
          />
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
          {page === "datasheets" && (
            <DatasheetsPage data={data} selectedId={selectedId} />
          )}
        </>
      )}
    </>
  );
}
