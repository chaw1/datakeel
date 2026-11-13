import { Icon } from "../components/Icon";
import { kindLabels } from "../features/object/descriptors";
import { objectTabsFor } from "../features/object/navigation";
import { localizedObjectName } from "../i18n/graphCatalogNames";
import { useI18n } from "../i18n/useI18n";

import {
  findNavLocation,
  objectTabLabels,
  operationPages,
  parentRouteForObject,
} from "./navigation";

import type { Page } from "./navigation";
import type { Dataset } from "../api/types";
import type { ObjectKind, ObjectTab } from "../features/object/navigation";

export function Breadcrumbs({
  page,
  navigate,
  selected,
  objectName,
  objectKind,
  objectTab,
  params,
}: {
  page: Page;
  navigate: (page: Page) => void;
  selected?: Dataset;
  objectName?: string;
  objectKind?: ObjectKind;
  objectTab?: ObjectTab;
  params?: URLSearchParams;
}) {
  const { t, locale } = useI18n();
  const operation = operationPages.find((item) => item.id === page);
  const loc = findNavLocation(page, objectKind);
  const runType = params?.get("type");
  const showObjectTab =
    objectKind && objectTab && objectTabsFor(objectKind).includes(objectTab);

  function renderTrail() {
    if (page === "workbench") {
      return (
        <>
          <Icon name="chevron" size={12} />
          <span className="breadcrumb-current" aria-current="page">
            {t("workbench")}
          </span>
        </>
      );
    }
    if (page === "labeling") {
      return (
        <>
          <Icon name="chevron" size={12} />
          <button
            type="button"
            className="breadcrumb-link"
            onClick={() => {
              navigate("workbench");
            }}
          >
            {t("workbench")}
          </button>
          <Icon name="chevron" size={12} />
          <span className="breadcrumb-current" aria-current="page">
            {t("wbNav")}
          </span>
        </>
      );
    }
    if (page === "object") {
      const parent = objectKind ? parentRouteForObject(objectKind) : undefined;
      const objectLabel =
        locale === "en" && objectName && objectKind
          ? localizedObjectName(objectKind, objectName, locale)
          : t("pageObject");
      return (
        <>
          {parent && objectKind && (
            <>
              <Icon name="chevron" size={12} />
              <button
                type="button"
                className="breadcrumb-link"
                onClick={() => {
                  navigate(parent.page);
                }}
              >
                {t(parent.label)}
              </button>
              <Icon name="chevron" size={12} />
              <span className="breadcrumb-kind">
                {t(kindLabels[objectKind])}
              </span>
            </>
          )}
          <Icon name="chevron" size={12} />
          <span className="breadcrumb-current" aria-current="page">
            {objectLabel}
          </span>
          {showObjectTab && (
            <span className="breadcrumb-tab">
              {t(objectTabLabels[objectTab])}
            </span>
          )}
        </>
      );
    }
    if (page === "runs" && (runType === "pipeline" || runType === "action")) {
      return (
        <>
          <Icon name="chevron" size={12} />
          <span className="breadcrumb-group">{t("operationsGroup")}</span>
          <Icon name="chevron" size={12} />
          <button
            type="button"
            className="breadcrumb-link"
            onClick={() => {
              navigate("runs");
            }}
          >
            {t("runRecords")}
          </button>
          <Icon name="chevron" size={12} />
          <span className="breadcrumb-current" aria-current="page">
            {t(runType === "pipeline" ? "pipelineType" : "actionType")}
          </span>
        </>
      );
    }
    const label = operation
      ? t(operation.label)
      : page === "runs"
        ? t("runRecords")
        : page === "quality" || page === "quality-rules"
          ? t(page === "quality" ? "dataQuality" : "dqNav")
          : page === "datasets"
            ? t("dataLibraryLabel")
            : loc
              ? t(loc.itemLabel)
              : (selected?.name ?? t("workspaceLabel"));
    return (
      <>
        {loc && loc.groupId !== "workbench" && (
          <>
            <Icon name="chevron" size={12} />
            <span className="breadcrumb-group">{t(loc.groupLabel)}</span>
          </>
        )}
        <Icon name="chevron" size={12} />
        <span className="breadcrumb-current" aria-current="page">
          {label}
        </span>
      </>
    );
  }

  return (
    <nav className="breadcrumb" aria-label={t("breadcrumbNav")}>
      <button
        type="button"
        className="breadcrumb-link"
        onClick={() => {
          navigate("workbench");
        }}
      >
        {t("workspaceLabel")}
      </button>
      {renderTrail()}
    </nav>
  );
}
