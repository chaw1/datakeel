import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import { RegistryBrowser } from "../features/ontology/RegistryBrowser";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { OntologyRegistry } from "../api/types";
export function OntologyPage() {
  const { t } = useI18n();
  const resource = useResource<OntologyRegistry>("/api/ontology");
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>
            {t("pageCount", {
              name: t("ontologyNav"),
              count: resource.value
                ? resource.value.object_types.length +
                  resource.value.link_types.length +
                  resource.value.functions.length +
                  resource.value.actions.length
                : 0,
            })}
          </h1>
        </div>
        <button className="button" onClick={resource.reload}>
          <Icon name="refresh" />
          {t("refresh")}
        </button>
      </div>
      <ResourceState {...resource} onRetry={resource.reload} />
      {resource.value && <RegistryBrowser registry={resource.value} />}
    </>
  );
}
