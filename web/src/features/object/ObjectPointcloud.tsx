import { Fragment, useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";
import type { MessageKey } from "../../i18n/en";

const unitReasons: Partial<Record<string, MessageKey>> = {
  extent_exceeds_expected_maximum_possible_millimeters:
    "objPointcloudUnitExtent",
  batch_extent_ratio_possible_unit_mismatch: "objPointcloudUnitComparison",
};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function ObjectPointcloud({
  data,
  target,
}: {
  data: ObjectData;
  target: ObjectTarget;
}) {
  const { t, locale } = useI18n();
  const [failedPreview, setFailedPreview] = useState("");
  const file = data.file;
  const probe = record(file?.metadata?.pointcloud_probe);
  if (!file || !probe) return null;
  const number = new Intl.NumberFormat(locale, { maximumSignificantDigits: 6 });
  const integer = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const count = (input: unknown): string =>
    typeof input === "number" && Number.isSafeInteger(input)
      ? integer.format(input)
      : t("objNoSource");
  const value = (input: unknown): string => {
    if (typeof input === "number" && Number.isFinite(input))
      return number.format(input);
    if (typeof input === "string" && input) return input;
    if (Array.isArray(input) && input.length)
      return input.map((item: unknown) => value(item)).join(", ");
    return t("objNoSource");
  };
  const ratio = (input: unknown): string =>
    typeof input === "number" && Number.isFinite(input)
      ? new Intl.NumberFormat(locale, {
          style: "percent",
          maximumFractionDigits: 2,
        }).format(input)
      : t("objNoSource");
  const bounds = record(probe.bounding_box);
  const facts: [MessageKey, string][] = [
    ["objPointcloudFormat", value(probe.format)],
    ["objPointcloudEncoding", value(probe.encoding)],
    ["objPointcloudPoints", count(probe.point_count)],
    ["objPointcloudFields", value(probe.fields)],
    ["objPointcloudBoundsMin", value(bounds?.min)],
    ["objPointcloudBoundsMax", value(bounds?.max)],
    ["objPointcloudDensity", value(probe.density)],
    ["objPointcloudNan", count(probe.nan_count)],
    ["objPointcloudInf", count(probe.inf_count)],
    ["objPointcloudInvalid", ratio(probe.invalid_ratio)],
    ["objPointcloudOutliers", ratio(probe.outlier_ratio)],
    ["objPointcloudOutlierSample", count(probe.outlier_sample_count)],
    [
      "objPointcloudUnits",
      typeof probe.unit_suspected === "boolean"
        ? t(
            probe.unit_suspected
              ? "objPointcloudUnitWarning"
              : "objPointcloudUnitOk",
          )
        : t("objNoSource"),
    ],
  ];
  const datasetId =
    data.dataset?.id ?? target.datasetId ?? data.target.datasetId;
  const versionId =
    target.versionId ?? data.version?.id ?? data.target.versionId;
  const query = versionId
    ? `?${new URLSearchParams({ version: versionId }).toString()}`
    : "";
  const preview = record(file.metadata?.pointcloud_preview);
  const previewUrl =
    preview && datasetId
      ? `/api/datasets/${encodeURIComponent(datasetId)}/files/${encodeURIComponent(file.id)}/pointcloud-preview${query}`
      : "";
  const unitReason =
    typeof probe.unit_reason === "string" ? probe.unit_reason : "";
  const unitReasonLabel = unitReasons[unitReason];
  return (
    <section
      className="object-source-detail object-pointcloud"
      aria-label={t("objPointcloud")}
    >
      <h2>{t("objPointcloud")}</h2>
      <dl>
        {facts.map(([label, content]) => (
          <Fragment key={label}>
            <dt>{t(label)}</dt>
            <dd>{content}</dd>
          </Fragment>
        ))}
      </dl>
      {unitReason && <p>{unitReasonLabel ? t(unitReasonLabel) : unitReason}</p>}
      <h3>{t("objPointcloudPreview")}</h3>
      {previewUrl && failedPreview !== previewUrl ? (
        <figure>
          <img
            src={previewUrl}
            alt={t("objPointcloudPreviewAlt", { name: file.filename })}
            onError={() => {
              setFailedPreview(previewUrl);
            }}
          />
          <figcaption>{t("objPointcloudPreviewCaption")}</figcaption>
        </figure>
      ) : (
        <p className="muted" role={previewUrl ? "status" : undefined}>
          {t(
            previewUrl
              ? "objPointcloudPreviewFailed"
              : "objPointcloudPreviewMissing",
          )}
        </p>
      )}
    </section>
  );
}
