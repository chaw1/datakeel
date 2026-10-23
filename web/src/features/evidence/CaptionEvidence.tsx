import { Anchor } from "../../components/Anchor";
import { useI18n } from "../../i18n/useI18n";

import type { EvidenceSample } from "../../api/types";
import type { AnchorRange } from "../../components/Anchor";

export function CaptionEvidence({
  caption,
  spans,
  ranges,
  activeId,
  onActive,
}: {
  caption: string | null;
  spans: EvidenceSample["caption_spans"];
  ranges?: AnchorRange[];
  activeId?: string;
  onActive?: (id: string) => void;
}) {
  const { t } = useI18n();
  if (caption === null) return <p className="muted">{t("evNoCaption")}</p>;
  return (
    <p className="caption-evidence">
      <Anchor
        text={caption}
        ranges={
          ranges ??
          spans.map((span, index) => ({
            ...span,
            id: String(index),
            number: index + 1,
          }))
        }
        activeId={activeId}
        onActive={onActive}
      />
    </p>
  );
}
