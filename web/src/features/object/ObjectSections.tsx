import { useI18n } from "../../i18n/useI18n";
import { Files } from "../files/Files";
import Quality from "../quality/Quality";
import { ReportView } from "../reports/ReportView";
import { Versions } from "../versions/Versions";

import { ObjectEvidence } from "./ObjectEvidence";
import { ObjectFileQuality } from "./ObjectFileQuality";
import { ObjectHistory } from "./ObjectHistory";
import { ObjectMedia } from "./ObjectMedia";
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
        <Versions
          versions={data.versions}
          datasetId={data.dataset?.id ?? target.id}
        />
      );
    case "quality":
      return target.kind === "file" ? (
        <>
          <ObjectMedia data={data} target={target} />
          <ObjectFileQuality data={data} />
        </>
      ) : (
        <Quality quality={data.quality} />
      );
    case "report":
      return <ReportView report={data.report} />;
    case "facts":
      return (
        <>
          <ObjectMedia data={data} target={target} />
          <section
            id="object-section-source-record"
            className="object-source-evidence"
          >
            <h2>{t("objSourceRecord")}</h2>
            <p>{data.metric?.definition.description ?? data.name}</p>
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
          </section>
        </>
      );
  }
}
