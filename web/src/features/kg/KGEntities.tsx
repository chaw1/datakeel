import { useI18n } from "../../i18n/useI18n";

import type { KGEntity } from "../../api/kg";

export function KGEntities({
  entities,
  onInspect,
}: {
  entities: KGEntity[];
  onInspect: (entity: KGEntity) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>{t("kgEntities")}</th>
            <th>{t("kgType")}</th>
            <th>{t("kgMentions")}</th>
            <th>{t("kgSource")}</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((entity) => (
            <tr key={entity.asset_ref.asset_id}>
              <td>
                <strong>{entity.name}</strong>
              </td>
              <td>{entity.type}</td>
              <td>{entity.mention_count}</td>
              <td>
                <button
                  className="text-button"
                  onClick={() => {
                    onInspect(entity);
                  }}
                >
                  {t("kgOccurrences")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!entities.length && <p className="kg-empty">{t("kgEmpty")}</p>}
    </div>
  );
}
