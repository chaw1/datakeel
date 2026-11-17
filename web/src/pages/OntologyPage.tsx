import { ResourceState } from "../components/ResourceState";
import { Button, PageHeader } from "../components/ui";
import { RegistryBrowser } from "../features/ontology/RegistryBrowser";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { OntologyRegistry } from "../api/types";

export function OntologyPage() {
  const { t } = useI18n();
  const resource = useResource<OntologyRegistry>("/api/ontology");
  return (
    <>
      <PageHeader
        title={t("pageCount", {
          name: t("ontologyNav"),
          count: resource.value
            ? resource.value.object_types.length +
              resource.value.link_types.length +
              resource.value.functions.length +
              resource.value.actions.length
            : 0,
        })}
        actions={
          <Button icon="refresh" onClick={resource.reload}>
            {t("refresh")}
          </Button>
        }
      />
      <ResourceState {...resource} onRetry={resource.reload} />
      {resource.value && <RegistryBrowser registry={resource.value} />}
    </>
  );
}
