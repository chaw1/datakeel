import { useState } from "react";

import { Icon } from "../components/Icon";
import { Badge, Button, EmptyState, Input, PageHeader } from "../components/ui";
import { objectHref } from "../features/object/navigation";
import { useI18n } from "../i18n/useI18n";
import { date, display } from "../lib/format";

import type { Dataset } from "../api/types";
import type { Page } from "../app/navigation";
export function LibraryPage({
  datasets,
  loading,
  setRefresh,
  setSelectedId,
}: {
  datasets: Dataset[];
  loading: boolean;
  setRefresh: React.Dispatch<React.SetStateAction<number>>;
  setSelectedId: (id: string) => void;
  navigate: (page: Page) => void;
}) {
  const { t, locale } = useI18n();
  const [search, setSearch] = useState("");
  return (
    <>
      <PageHeader
        title={t("datasetCountTitle", { count: datasets.length })}
        actions={
          <Button
            icon="refresh"
            iconSize={16}
            onClick={() => {
              setRefresh((value) => value + 1);
            }}
          >
            {t("refresh")}
          </Button>
        }
      />
      <div className="library-stats">
        <div>
          <span className="stat-symbol">
            <Icon name="database" />
          </span>
          <div>
            <strong>{datasets.length}</strong>
            <span>{t("datasets")}</span>
          </div>
        </div>
        <div>
          <span className="stat-symbol">
            <Icon name="file" />
          </span>
          <div>
            <strong>
              {datasets
                .reduce((sum, dataset) => sum + (dataset.file_count || 0), 0)
                .toLocaleString()}
            </strong>
            <span>{t("filesInYourLibrary")}</span>
          </div>
        </div>
        <div>
          <span className="stat-symbol">
            <Icon name="lineage" />
          </span>
          <div>
            <strong>{t("connected")}</strong>
            <span>{t("lineageQualityAndReports")}</span>
          </div>
        </div>
      </div>
      <div className="section-heading library-heading">
        <h2>
          {t("dataLibraryLabel")}{" "}
          <span className="count-pill">{datasets.length}</span>
        </h2>
        <Input
          icon="search"
          wrapperClassName="search-field"
          aria-label={t("searchDatasets")}
          placeholder={t("findADataset")}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
        />
      </div>
      <div className="dataset-grid">
        {datasets
          .filter((dataset) =>
            dataset.name.toLowerCase().includes(search.toLowerCase()),
          )
          .map((dataset) => (
            <button
              key={dataset.id}
              className="dataset-card"
              onClick={() => {
                setSelectedId(dataset.id);
                window.location.hash = objectHref({
                  kind: "dataset",
                  id: dataset.id,
                  tab: "facts",
                });
              }}
            >
              <div className="dataset-card-top">
                <span className="dataset-symbol">
                  <Icon name="database" size={23} />
                </span>
                <Badge>{t("dataset")}</Badge>
              </div>
              <h3>{dataset.name}</h3>
              <p>
                {display(
                  dataset.metadata.description,
                  t("aVersionedCollectionOfDataReadyToExplore"),
                )}
              </p>
              <div className="dataset-card-meta">
                <span>
                  <Icon name="file" size={14} />
                  {dataset.file_count}{" "}
                  {t("files", { count: dataset.file_count })}{" "}
                </span>
                <span>
                  <Icon name="clock" size={14} />
                  {date(dataset.created_at, locale)}
                </span>
              </div>
              <div className="dataset-card-bottom">
                <span>{t("exploreDataset")}</span>
                <Icon name="arrow" size={17} />
              </div>
            </button>
          ))}
      </div>
      {!datasets.length && (
        <EmptyState
          card
          icon="database"
          title={loading ? t("openingYourWorkspace") : t("yourLibraryIsReady")}
          description={
            loading
              ? t("connectingToTheLocalApi")
              : t("runDatakeelDemoToImportTheSampleDatasetAndStartAPipeline")
          }
        />
      )}
    </>
  );
}
