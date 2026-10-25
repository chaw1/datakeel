import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import type { KGSource } from "../../api/kg";
import type { Assertion } from "../../api/types";

export function KGImageSource({
  source,
  anchors,
}: {
  source: KGSource;
  anchors: Assertion["anchors"];
}) {
  const { t } = useI18n();
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const failed = !source.image_url || failedUrl === source.image_url;
  const regions = anchors.flatMap((anchor) =>
    anchor.asset_ref.asset_id === source.asset_ref.asset_id &&
    anchor.selector?.type === "image_region"
      ? [anchor.selector]
      : [],
  );
  const colors = ["var(--red)", "var(--ok)", "var(--warn)", "var(--ink)"];
  return (
    <section className="kg-source kg-image-source">
      <h3>{source.filename}</h3>
      {failed ? (
        <p className="kg-missing" role="status">
          {t("kgImageLoadFailed")}
        </p>
      ) : (
        <p className={regions.length ? "" : "kg-missing"}>
          {t(regions.length ? "kgImageLocated" : "kgImageUnlocated")}
        </p>
      )}
      {!failed && source.image_url && (
        <div className="kg-image">
          <img
            src={source.image_url}
            alt={source.filename}
            loading="lazy"
            onError={() => {
              setFailedUrl(source.image_url ?? null);
            }}
          />
          {regions.map((region, index) => (
            <span
              className="kg-image-region"
              key={index}
              role="img"
              aria-label={t("kgImageRegion", { number: index + 1 })}
              style={{
                borderColor: colors[index % colors.length],
                color: colors[index % colors.length],
                left: `${String((region.bbox[0] * 100) / region.width)}%`,
                top: `${String((region.bbox[1] * 100) / region.height)}%`,
                width: `${String(((region.bbox[2] - region.bbox[0]) / region.width) * 100)}%`,
                height: `${String(((region.bbox[3] - region.bbox[1]) / region.height) * 100)}%`,
              }}
            >
              <span>{index + 1}</span>
            </span>
          ))}
        </div>
      )}
      <p className="muted">
        {t("kgImageCoordinates")} · {source.width} × {source.height}
      </p>
      {!failed && (
        <ol className="kg-image-coordinates">
          {regions.map((region, index) => (
            <li key={index}>
              <code>{region.bbox.join(", ")}</code>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
