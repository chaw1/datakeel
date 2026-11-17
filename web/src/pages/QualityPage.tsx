import { useState } from "react";

import { ResourceState } from "../components/ResourceState";
import { Badge, Select, Surface } from "../components/ui";
import Quality from "../features/quality/Quality";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { DatasetData } from "../api/types";

export function QualityPage({
  data,
  selectedId,
}: {
  data: DatasetData;
  selectedId: string;
}) {
  const { t } = useI18n();
  const [quarantine, setQuarantine] = useState("all");
  const resource = useResource(
    quarantine === "all"
      ? null
      : `/api/datasets/${encodeURIComponent(selectedId)}/quality?quarantined=${quarantine}`,
    data.quality,
  );
  return (
    <Surface as="section">
      <div className="card-heading">
        <div>
          <h2>{t("dataQuality")}</h2>
          <p>
            {t("weightedScoresForTheLatestVersionWithFindingsYouCanActOn")}{" "}
          </p>
        </div>
        <Badge>{t("fiveDimensions")}</Badge>
      </div>
      <div className="table-toolbar">
        <label htmlFor="quality-quarantine">{t("filterQuarantine")}</label>
        <Select
          id="quality-quarantine"
          value={quarantine}
          onChange={(event) => {
            setQuarantine(event.target.value);
          }}
          onBlur={(event) => {
            setQuarantine(event.target.value);
          }}
        >
          <option value="all">{t("allFiles")}</option>
          <option value="false">{t("notQuarantined")}</option>
          <option value="true">{t("quarantined")}</option>
        </Select>
      </div>
      <ResourceState {...resource} onRetry={resource.reload} />
      {!resource.loading && !resource.error && (
        <Quality quality={resource.value} />
      )}
    </Surface>
  );
}
