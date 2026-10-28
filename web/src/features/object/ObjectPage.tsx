import { useEffect } from "react";

import { ResourceState } from "../../components/ResourceState";
import { localizedObjectName } from "../../i18n/graphCatalogNames";
import { useI18n } from "../../i18n/useI18n";
import { MetadataEvidence } from "../catalog/MetadataEvidence";
import { TableQualityRules } from "../qualityRules/TableQualityRules";

import { objectHref, readObjectTarget } from "./navigation";
import { ObjectFacts } from "./ObjectFacts";
import { ObjectHeader } from "./ObjectHeader";
import { ObjectSections } from "./ObjectSections";
import { useObject } from "./useObject";
import "./object.css";

import type { ObjectTab, ObjectTarget } from "./navigation";
import type { MessageKey } from "../../i18n/en";
import type { MouseEvent } from "react";

const labels: Record<ObjectTab, MessageKey> = {
  facts: "objFacts",
  relations: "objRelations",
  evidence: "objEvidence",
  history: "objHistory",
  files: "filesTab",
  versions: "versions",
  quality: "quality",
  "annotation-quality": "annotationQuality",
  "text-governance": "trainingTitle",
  report: "report",
  datasheets: "datasheets",
};
export function ObjectPage({
  target,
  onOpen,
  onDataChanged,
  onNameChange,
}: {
  target: ObjectTarget;
  onOpen?: (target: ObjectTarget) => void;
  onDataChanged?: () => void;
  onNameChange?: (target: ObjectTarget, name: string) => void;
}) {
  const { t, locale } = useI18n();
  const resource = useObject(target);
  const data = resource.value;
  const tab = target.tab ?? "relations";
  useEffect(() => {
    if (data)
      onNameChange?.(
        data.target,
        localizedObjectName(
          data.target.kind,
          data.name,
          locale,
          data.englishName,
        ),
      );
  }, [data, onNameChange, locale]);
  useEffect(() => {
    const ids = [
      target.eventId && `object-event-${target.eventId}`,
      target.eventId && `object-audit-${target.eventId}`,
      target.section && `object-section-${target.section}`,
    ];
    for (const id of ids) {
      const element = id ? document.getElementById(id) : null;
      if (element) {
        element.scrollIntoView({ block: "nearest" });
        break;
      }
    }
  }, [data, target.eventId, target.section, tab]);
  function open(next: ObjectTarget) {
    if (onOpen) onOpen(next);
    else window.location.hash = objectHref(next);
  }
  function follow(event: MouseEvent<HTMLElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)
      return;
    const element = event.target;
    const href =
      element instanceof Element
        ? element.closest("a")?.getAttribute("href")
        : null;
    if (!href) return;
    const next = readObjectTarget(href);
    if (next) {
      event.preventDefault();
      open(next);
    } else if (href.startsWith("#chapter-")) {
      event.preventDefault();
      document
        .getElementById(href.slice(1))
        ?.scrollIntoView({ block: "start" });
    }
  }
  const tabs: ObjectTab[] = ["facts", "relations", "evidence", "history"];
  if (target.kind === "dataset")
    tabs.push(
      "files",
      "versions",
      "quality",
      "annotation-quality",
      "text-governance",
      "report",
      "datasheets",
    );
  if (target.kind === "version")
    tabs.push("files", "annotation-quality", "text-governance");
  if (target.kind === "file") tabs.push("quality");
  const resolved = {
    ...target,
    datasetId: data?.target.datasetId ?? target.datasetId,
  };
  return (
    <article
      className="object-page"
      aria-label={t("objTitle")}
      onClickCapture={follow}
    >
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {data && (
        <>
          <ObjectHeader data={data} target={resolved} />
          <ObjectFacts data={data} target={resolved} />
          {target.kind === "table" && data.catalog && (
            <TableQualityRules table={data.catalog} />
          )}
          {data.catalog && <MetadataEvidence item={data.catalog} />}
          <nav className="tabs object-tabs" aria-label={t("objTitle")}>
            {tabs.map((value) => (
              <a
                className={tab === value ? "active" : ""}
                aria-current={tab === value ? "page" : undefined}
                key={value}
                href={objectHref({
                  ...resolved,
                  tab: value,
                  eventId: undefined,
                  relation: undefined,
                  section: undefined,
                })}
              >
                {t(labels[value])}
              </a>
            ))}
          </nav>
          <div className="object-body">
            <ObjectSections
              data={data}
              target={resolved}
              onOpen={open}
              reload={() => {
                resource.reload();
                onDataChanged?.();
              }}
            />
          </div>
        </>
      )}
    </article>
  );
}
