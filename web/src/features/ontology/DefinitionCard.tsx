import { useI18n } from "../../i18n/useI18n";

import type { OntologyRegistry } from "../../api/types";
import type { MessageKey } from "../../i18n/en";

type Definition =
  | OntologyRegistry["object_types"][number]
  | OntologyRegistry["link_types"][number]
  | OntologyRegistry["functions"][number]
  | OntologyRegistry["actions"][number];
export function DefinitionCard({
  entry,
  category,
}: {
  entry: Definition;
  category: MessageKey;
}) {
  const { t } = useI18n();
  return (
    <article className="card definition-card">
      <div className="definition-heading">
        <span className="badge gray">{t(category)}</span>
        <span className="muted small">
          {t("schemaVersion", { version: entry.version })}
        </span>
      </div>
      <h3>{entry.id}</h3>
      <dl className="detail-grid">
        {"identity_mapping" in entry && (
          <div>
            <dt>{t("identityMapping")}</dt>
            <dd>
              {entry.identity_mapping.asset_type} ·{" "}
              <code>{entry.identity_mapping.id_field}</code>
            </dd>
          </div>
        )}
        {"semantics" in entry && (
          <>
            <div>
              <dt>{t("semantics")}</dt>
              <dd>{entry.semantics}</dd>
            </div>
            <div>
              <dt>{t("cardinality")}</dt>
              <dd>{entry.cardinality}</dd>
            </div>
            <div>
              <dt>{t("domain")}</dt>
              <dd>{entry.domain.join(", ")}</dd>
            </div>
            <div>
              <dt>{t("range")}</dt>
              <dd>{entry.range.join(", ")}</dd>
            </div>
          </>
        )}
        {"read_scope" in entry && (
          <div>
            <dt>{t("readScope")}</dt>
            <dd>
              <code>{entry.read_scope}</code>
            </dd>
          </div>
        )}
        {"auth_scope" in entry && (
          <>
            <div>
              <dt>{t("authScope")}</dt>
              <dd>
                <code>{entry.auth_scope}</code>
              </dd>
            </div>
            <div>
              <dt>{t("reversibility")}</dt>
              <dd>
                {t(
                  entry.reversible ? "reversibleAction" : "irreversibleAction",
                )}
              </dd>
            </div>
            {entry.inverse_of && (
              <div>
                <dt>{t("inverseAction")}</dt>
                <dd>{entry.inverse_of}</dd>
              </div>
            )}
          </>
        )}
      </dl>
      {"description" in entry && <p className="muted">{entry.description}</p>}
      {"preconditions" in entry && (
        <>
          <h4>{t("preconditions")}</h4>
          <ul>
            {entry.preconditions.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
          <h4>{t("effects")}</h4>
          <ul>
            {entry.effects.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
        </>
      )}
      <details>
        <summary>{t("schema")}</summary>
        <pre>{JSON.stringify(entry, null, 2)}</pre>
      </details>
    </article>
  );
}
