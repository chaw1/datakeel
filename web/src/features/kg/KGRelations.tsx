import { useI18n } from "../../i18n/useI18n";

import { KGBadge } from "./KGBadge";

import type { KGRelation } from "../../api/kg";

export function KGRelations({
  relations,
  selected,
  onSelect,
  onInspect,
}: {
  relations: KGRelation[];
  selected: string[];
  onSelect: (ids: string[]) => void;
  onInspect: (id: string) => void;
}) {
  const { t } = useI18n();
  const rows = [...relations].sort(
    (a, b) =>
      Number(b.assertion.verification === "needs_review") -
      Number(a.assertion.verification === "needs_review"),
  );
  const ids = rows.flatMap((row) =>
    row.assertion.id ? [row.assertion.id] : [],
  );
  return (
    <div className="table-scroll">
      <table className="kg-relations">
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                aria-label={t("kgSelectAll")}
                checked={
                  ids.length > 0 && ids.every((id) => selected.includes(id))
                }
                onChange={(event) => {
                  onSelect(event.target.checked ? ids : []);
                }}
              />
            </th>
            <th>{t("kgHead")}</th>
            <th>{t("kgPredicate")}</th>
            <th>{t("kgTail")}</th>
            <th>{t("kgStatus")}</th>
            <th>{t("kgVerification")}</th>
            <th>{t("kgExtractor")}</th>
            <th>{t("kgEvidence")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const id = row.assertion.id ?? "";
            return (
              <tr
                key={id}
                data-relation-id={id}
                data-verification={row.assertion.verification}
              >
                <td>
                  <input
                    type="checkbox"
                    aria-label={t("kgSelect", {
                      name: `${row.head.name} ${row.assertion.predicate} ${row.tail.name}`,
                    })}
                    checked={selected.includes(id)}
                    disabled={!id}
                    onChange={(event) => {
                      onSelect(
                        event.target.checked
                          ? [...selected, id]
                          : selected.filter((item) => item !== id),
                      );
                    }}
                  />
                </td>
                <td>
                  <strong>{row.head.name}</strong>
                  <small>{row.head.type}</small>
                </td>
                <td>
                  <code>{row.assertion.predicate.replace(/^kg\./, "")}</code>
                </td>
                <td>
                  <strong>{row.tail.name}</strong>
                  <small>{row.tail.type}</small>
                </td>
                <td>
                  <KGBadge value={row.assertion.status} />
                </td>
                <td>
                  <KGBadge value={row.assertion.verification} />
                </td>
                <td>
                  {row.extractor}
                  <small>{row.model}</small>
                </td>
                <td>
                  <button
                    className="text-button"
                    onClick={() => {
                      onInspect(id);
                    }}
                  >
                    {t("kgInspect")}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!rows.length && <p className="kg-empty">{t("kgEmpty")}</p>}
    </div>
  );
}
