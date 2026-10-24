import { Anchor } from "../../components/Anchor";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import type { KGSource } from "../../api/kg";
import type { Assertion } from "../../api/types";

export function KGSourcePreview({
  fileId,
  versionId,
  anchors,
}: {
  fileId: string;
  versionId: string;
  anchors: Assertion["anchors"];
}) {
  const { t } = useI18n();
  const source = useResource<KGSource>(
    `/api/kg/sources/${encodeURIComponent(fileId)}?version_id=${encodeURIComponent(versionId)}`,
  );
  const ranges = anchors.flatMap((anchor, index) =>
    anchor.selector?.type === "text_span"
      ? [
          {
            ...anchor.selector,
            id: `${fileId}:${String(index)}`,
            number: index + 1,
          },
        ]
      : [],
  );
  return (
    <section className="kg-source">
      <ResourceState {...source} onRetry={source.reload} />
      {source.value && (
        <>
          <h4>{source.value.filename}</h4>
          <p className="kg-source-text">
            <Anchor text={source.value.text} ranges={ranges} />
          </p>
        </>
      )}
      <ul className="kg-locations">
        {anchors.map((anchor, index) => (
          <li key={index}>
            {anchor.selector?.type === "text_span"
              ? t("kgOffsets", anchor.selector)
              : t("kgWhole")}
          </li>
        ))}
      </ul>
    </section>
  );
}
