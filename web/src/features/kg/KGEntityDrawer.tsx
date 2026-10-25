import { useEffect, useRef } from "react";

import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { KGAssetLinks } from "./KGAssetLinks";
import { KGSourcePreview } from "./KGSourcePreview";

import type { KGEntity } from "../../api/kg";

export function KGEntityDrawer({
  entity,
  versionId,
  onClose,
  onChanged,
}: {
  entity: KGEntity;
  versionId: string;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    if (dialog.current?.showModal) dialog.current.showModal();
    else dialog.current?.setAttribute("open", "");
    return () => {
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  const anchors = entity.mentions.flatMap((mention) => mention.anchors);
  const files = [
    ...new Set(anchors.map((anchor) => anchor.asset_ref.asset_id)),
  ];
  return (
    <dialog
      className="kg-drawer"
      ref={dialog}
      aria-label={t("kgOccurrences")}
      onKeyDown={(event) => {
        if (
          isComposing(event.nativeEvent) &&
          (event.key === "Escape" || event.key === "Enter")
        )
          event.preventDefault();
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!isComposing()) onClose();
      }}
    >
      <header>
        <div>
          <span className="eyebrow">{t("kgOccurrences")}</span>
          <h2>{entity.name}</h2>
          <p>
            {entity.type} · {t("kgMentions")}: {entity.mention_count}
          </p>
        </div>
        <button className="button" aria-label={t("kgClose")} onClick={onClose}>
          ×
        </button>
      </header>
      {["dataset", "metric"].includes(entity.type.toLowerCase()) && (
        <KGAssetLinks
          entityId={entity.asset_ref.asset_id}
          onChanged={onChanged}
        />
      )}
      {!files.length && <p>{t("kgEmptyMentions")}</p>}
      {files.map((id) => (
        <KGSourcePreview
          key={id}
          fileId={id}
          versionId={
            anchors.find((anchor) => anchor.asset_ref.asset_id === id)
              ?.asset_ref.version ?? versionId
          }
          anchors={anchors.filter((anchor) => anchor.asset_ref.asset_id === id)}
        />
      ))}
    </dialog>
  );
}
