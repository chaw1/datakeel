import { useI18n } from "../../i18n/useI18n";
import { Releases } from "../releases/Releases";
import { TrainingSets } from "../training/TrainingSets";

import { VersionCompare } from "./VersionCompare";
import { Versions } from "./Versions";
import "./versions.css";

import type { Version } from "../../api/types";

export function VersionWorkspace({
  versions,
  datasetId,
  onChanged,
}: {
  versions: Version[];
  datasetId: string;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  return (
    <div className="version-workspace">
      <TrainingSets datasetId={datasetId} versions={versions} />
      <VersionCompare versions={versions} datasetId={datasetId} />
      <Releases
        versions={versions}
        datasetId={datasetId}
        onChanged={onChanged}
      />
      <section aria-label={t("versionHistory")}>
        <Versions versions={versions} datasetId={datasetId} />
      </section>
    </div>
  );
}
