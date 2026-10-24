import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { objectHref } from "../object/navigation";

import { KGBadge } from "./KGBadge";

import type { EntityLink } from "../../api/kg";

export function KGLinkTable({
  links,
  selected,
  busy,
  onSelect,
  onDecide,
}: {
  links: EntityLink[];
  selected: string[];
  busy: boolean;
  onSelect: (ids: string[]) => void;
  onDecide: (ids: string[], status: "accepted" | "rejected") => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const ids = links.flatMap((link) =>
    link.assertion.id ? [link.assertion.id] : [],
  );
  return (
    <div className="table-scroll">
      <table className="kg-link-table">
        <caption>{t("kgLinkScope")}</caption>
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                aria-label={t("kgLinkSelectAll")}
                disabled={busy || !ids.length}
                checked={
                  ids.length > 0 && ids.every((id) => selected.includes(id))
                }
                onChange={(event) => {
                  onSelect(event.target.checked ? ids : []);
                }}
              />
            </th>
            <th>{t("kgHead")}</th>
            <th>{t("kgLinkTarget")}</th>
            <th>{t("kgLinkBasis")}</th>
            <th>{t("kgLinkMatch")}</th>
            <th>{t("kgStatus")}</th>
            <th>{t("actions")}</th>
          </tr>
        </thead>
        <tbody>
          {links.map((link) => {
            const id = link.assertion.id ?? "";
            const target = link.target.asset_ref;
            return (
              <tr key={id}>
                <td>
                  <input
                    type="checkbox"
                    disabled={busy || !id}
                    aria-label={t("kgLinkSelect", {
                      entity: link.entity.name,
                      target: link.target.name,
                    })}
                    checked={selected.includes(id)}
                    onChange={(event) => {
                      onSelect(
                        event.target.checked
                          ? [...selected, id]
                          : selected.filter((value) => value !== id),
                      );
                    }}
                  />
                </td>
                <td>
                  <strong>{link.entity.name}</strong>
                  <small>{link.entity.type}</small>
                </td>
                <td>
                  <a
                    href={objectHref({
                      kind: target.asset_type === "metric" ? "metric" : "table",
                      id: target.asset_id,
                    })}
                  >
                    {link.target.name}
                  </a>
                  <small>
                    <code>{target.asset_id}</code>
                  </small>
                </td>
                <td>
                  <ul>
                    {link.basis.map((basis) => (
                      <li key={basis}>{basis}</li>
                    ))}
                  </ul>
                </td>
                <td>
                  {t(
                    link.match_kind === "unique"
                      ? "kgLinkUnique"
                      : "kgLinkAmbiguous",
                  )}
                </td>
                <td>
                  <KGBadge value={link.assertion.status} />
                </td>
                <td>
                  <div className="kg-link-actions">
                    <button
                      type="button"
                      className="button"
                      onKeyDown={(event) => {
                        if (isComposing(event.nativeEvent))
                          event.preventDefault();
                      }}
                      disabled={
                        busy || !id || link.assertion.status === "accepted"
                      }
                      onClick={() => {
                        onDecide([id], "accepted");
                      }}
                    >
                      {t("kgLinkAccept")}
                    </button>
                    <button
                      type="button"
                      className="button danger"
                      onKeyDown={(event) => {
                        if (isComposing(event.nativeEvent))
                          event.preventDefault();
                      }}
                      disabled={
                        busy || !id || link.assertion.status === "rejected"
                      }
                      onClick={() => {
                        onDecide([id], "rejected");
                      }}
                    >
                      {t("kgLinkReject")}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
