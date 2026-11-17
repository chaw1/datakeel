import { useState } from "react";

import { EmptyState, Input, SegmentedTabs } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";

import { DefinitionCard } from "./DefinitionCard";

import type { OntologyRegistry } from "../../api/types";

const categories = [
  { id: "object_types", label: "objectTypes" },
  { id: "link_types", label: "linkTypes" },
  { id: "functions", label: "functions" },
  { id: "actions", label: "actions" },
] as const;
type Category = (typeof categories)[number]["id"];

export function RegistryBrowser({ registry }: { registry: OntologyRegistry }) {
  const { t } = useI18n();
  const [category, setCategory] = useState<Category>("object_types");
  const [query, setQuery] = useState("");
  const entries = registry[category].filter((entry) =>
    entry.id.toLowerCase().includes(query.toLowerCase()),
  );
  const label =
    categories.find((item) => item.id === category)?.label ?? "objectTypes";
  return (
    <>
      <SegmentedTabs
        label={t("ontologyCategory")}
        activeId={category}
        onSelect={setCategory}
        items={categories.map((item) => ({
          id: item.id,
          label: t(item.label),
          count: registry[item.id].length,
        }))}
      />
      <div className="section-heading">
        <h2>
          {t("ontologyTypes")}{" "}
          <span className="count-pill">{entries.length}</span>
        </h2>
        <Input
          icon="search"
          wrapperClassName="search-field"
          aria-label={t("searchOntology")}
          placeholder={t("searchOntology")}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
      </div>
      <div className="definition-grid">
        {entries.map((entry) => (
          <DefinitionCard
            key={`${category}:${entry.id}`}
            entry={entry}
            category={label}
          />
        ))}
      </div>
      {!entries.length && <EmptyState card title={t("noRegistryEntries")} />}
    </>
  );
}
