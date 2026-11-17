import { useEffect, useRef } from "react";

import { Badge } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";

import type { FolderImage, FolderSelection } from "./folder";

const previewLimit = 12;

function FolderRow({ image }: { image: FolderImage }) {
  const { t } = useI18n();
  const preview = useRef<HTMLImageElement>(null);
  useEffect(() => {
    const node = preview.current;
    if (!node) return;
    const url = URL.createObjectURL(image.file);
    node.src = url;
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [image.file]);

  return (
    <li className="import-sample">
      {image.readable ? (
        <img ref={preview} alt="" width={48} height={48} />
      ) : (
        <span className="import-thumb-placeholder" aria-hidden="true">
          ×
        </span>
      )}
      <div className="import-sample-details">
        <strong title={image.path}>{image.path}</strong>
        <small>
          {t("importCaptionLabel")}
          {image.caption ?? t("importMissing")}
        </small>
        <small>
          {t("importAnnotationLabel")}
          {image.annotation ?? t("importMissing")}
        </small>
      </div>
      {!image.readable && <Badge tone="warn">{t("importUnreadable")}</Badge>}
    </li>
  );
}

export function FolderPreview({ selection }: { selection: FolderSelection }) {
  const { t } = useI18n();
  const { images, ignored } = selection;
  const counters = {
    total: images.length,
    captions: images.filter((image) => image.caption).length,
    annotations: images.filter((image) => image.annotation).length,
  };
  const items = [...images]
    .sort((first, second) => Number(first.readable) - Number(second.readable))
    .slice(0, previewLimit);
  return (
    <div className="import-preview">
      <h3>{t("importPreview")}</h3>
      <div className="import-counter-row" role="status">
        <Badge>{t("importImageCount", { count: counters.total })}</Badge>
        <Badge>{t("importCaptionCount", { count: counters.captions })}</Badge>
        <Badge>
          {t("importAnnotationCount", { count: counters.annotations })}
        </Badge>
      </div>
      <ul className="import-file-list">
        {items.map((image) => (
          <FolderRow key={image.path} image={image} />
        ))}
      </ul>
      {images.length > items.length && (
        <p className="muted small">
          {t("importPreviewCount", {
            preview: items.length,
            total: images.length,
          })}
        </p>
      )}
      {ignored > 0 && (
        <p className="muted small">{t("importIgnored", { count: ignored })}</p>
      )}
    </div>
  );
}
