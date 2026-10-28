import { useI18n } from "../../i18n/useI18n";
import { AnnotationQuality } from "../annotation/AnnotationQuality";
import { Datasheets } from "../datasheets/Datasheets";
import { Files } from "../files/Files";
import Quality from "../quality/Quality";
import { ReportView } from "../reports/ReportView";
import { StandardsChecks } from "../standards/StandardsChecks";
import { TrainingGovernance } from "../training-data/TrainingGovernance";
import { VersionWorkspace } from "../versions/VersionWorkspace";

import { ObjectEvidence } from "./ObjectEvidence";
import { ObjectFileQuality } from "./ObjectFileQuality";
import { ObjectHistory } from "./ObjectHistory";
import { ObjectProfile } from "./ObjectProfile";
import { ObjectRelations } from "./ObjectRelations";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";

export function ObjectSections({
  data,
  target,
  reload,
  onOpen,
}: {
  data: ObjectData;
  target: ObjectTarget;
  reload: () => void;
  onOpen: (target: ObjectTarget) => void;
}) {
  const { t } = useI18n();
  switch (target.tab ?? "relations") {
    case "relations":
      return <ObjectRelations data={data} target={target} onOpen={onOpen} />;
    case "history":
      return <ObjectHistory data={data} target={target} reload={reload} />;
    case "evidence":
      return <ObjectEvidence data={data} target={target} reload={reload} />;
    case "files":
      return (
        <Files
          files={data.version?.manifest ?? data.files}
          versions={data.versions}
          datasetId={data.dataset?.id ?? target.datasetId ?? target.id}
          initialVersionId={data.version?.id}
        />
      );
    case "versions":
      return (
        <VersionWorkspace
          versions={data.versions}
          datasetId={data.dataset?.id ?? target.id}
          onChanged={reload}
        />
      );
    case "quality":
      return target.kind === "file" ? (
        <ObjectFileQuality data={data} />
      ) : (
        <Quality quality={data.quality} />
      );
    case "annotation-quality":
      return (
        <AnnotationQuality
          datasetId={data.dataset?.id ?? target.datasetId ?? target.id}
          versionId={data.version?.id ?? data.versions[0]?.id}
        />
      );
    case "text-governance":
      return (
        <TrainingGovernance
          key={`${target.kind}:${target.id}`}
          datasetId={data.dataset?.id ?? target.datasetId ?? target.id}
          versions={data.versions}
          files={data.files}
          initialVersionId={data.version?.id ?? target.versionId}
          initialOpen
          onChanged={reload}
        />
      );
    case "report":
      return <ReportView report={data.report} />;
    case "datasheets":
      return (
        <Datasheets
          key={data.dataset?.id ?? target.id}
          datasetId={data.dataset?.id ?? target.id}
          versions={data.versions}
          initialVersionId={target.versionId}
        />
      );
    case "facts":
      return (
        <section
          id="object-section-source-record"
          className="object-source-evidence"
        >
          <h2>{t("objSourceRecord")}</h2>
          <p>{data.metric?.definition.description ?? data.name}</p>
          <ObjectProfile object={data.catalog ?? data.table?.table} />
          <details>
            <summary>{t("objProperties")}</summary>
            <pre>
              {JSON.stringify(
                data.file ??
                  data.version ??
                  data.catalog ??
                  data.metric?.definition ??
                  data.action ??
                  data.dataset,
                null,
                2,
              )}
            </pre>
          </details>
          {(target.kind === "table" || target.kind === "column") && (
            <StandardsChecks
              tableId={
                target.kind === "table"
                  ? target.id
                  : target.id.split("/").slice(0, -1).join("/")
              }
              columnId={target.kind === "column" ? target.id : undefined}
            />
          )}
        </section>
      );
  }
}
