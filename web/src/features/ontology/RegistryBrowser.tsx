import { useState } from "react";

import { Icon } from "../../components/Icon";
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
      <nav className="tabs" aria-label={t("ontologyCategory")}>
        {categories.map((item) => (
          <button
            key={item.id}
            aria-current={category === item.id ? "page" : undefined}
            className={category === item.id ? "active" : ""}
            onClick={() => {
              setCategory(item.id);
            }}
          >
            {t(item.label)}
            <span>{registry[item.id].length}</span>
          </button>
        ))}
      </nav>
      <div className="section-heading">
        <h2>
          {t("ontologyTypes")}{" "}
          <span className="count-pill">{entries.length}</span>
        </h2>
        <label className="search-field">
          <Icon name="search" />
          <input
            aria-label={t("searchOntology")}
            placeholder={t("searchOntology")}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
          />
        </label>
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
      {!entries.length && (
        <div className="card empty-state">
          <p>{t("noRegistryEntries")}</p>
        </div>
      )}
    </>
  );
}
