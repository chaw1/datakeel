import { useI18n } from "../../i18n/useI18n";

import { objectHref } from "./navigation";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";
import type { MessageKey } from "../../i18n/en";

const issueLabels: Partial<Record<string, MessageKey>> = {
  black_frame: "mediaBlackFrame",
  solid_frame: "mediaSolidFrame",
  frozen_frame: "mediaFrozenFrame",
  blurred_frame: "mediaBlurredFrame",
  video_duplicate: "mediaVideoDuplicate",
  audio_silence: "mediaSilence",
  audio_clipping: "mediaClipping",
  audio_loudness: "mediaLoudness",
  audio_duplicate: "mediaAudioDuplicate",
};

export function ObjectMedia({
  data,
  target,
}: {
  data: ObjectData;
  target: ObjectTarget;
}) {
  const { t } = useI18n();
  const pinned = target.versionId ?? data.version?.id;
  const versions = [...data.versions]
    .filter((version) => !pinned || version.id === pinned)
    .sort((left, right) => right.created_at - left.created_at);
  const file =
    (pinned
      ? versions
          .flatMap((version) => version.manifest)
          .find((item) => item.id === target.id)
      : versions
          .flatMap((version) => version.manifest)
          .find((item) => item.id === target.id && item.media)) ?? data.file;
  const media = file?.media;
  if (
    !file ||
    target.kind !== "file" ||
    !["audio", "video"].includes(file.modality)
  )
    return null;
  const issues = media?.issues ?? [];
  const history = media?.history ?? [];
  const probe = media?.probe;
  const alignment = media?.alignment;
  const range = (start: number, end: number | null | undefined) =>
    t("mediaTimeRange", {
      start: (start / 1000).toFixed(3),
      end: end == null ? "…" : (end / 1000).toFixed(3),
    });
  const seen = new Set<string>();
  const clips = versions.flatMap((version) =>
    version.manifest
      .filter((item) => {
        const derived = item.media;
        if (
          item.id === file.id ||
          seen.has(item.id) ||
          !derived?.history?.some((step) =>
            ["video.segment", "audio.trim_silence"].includes(step.operator),
          ) ||
          (derived.source_asset_id !== file.id &&
            derived.source_file_id !== file.id)
        )
          return false;
        seen.add(item.id);
        return true;
      })
      .map((item) => ({ file: item, versionId: version.id })),
  );
  return (
    <section className="object-source-detail" aria-label={t("mediaTitle")}>
      <h2>{t("mediaTitle")}</h2>
      {probe ? (
        <dl>
          <dt>{t("mediaDuration")}</dt>
          <dd>
            {t("mediaSeconds", {
              value: (probe.duration_ms / 1000).toFixed(3),
            })}
          </dd>
          <dt>{t("mediaEncoding")}</dt>
          <dd>
            {probe.codec || "—"} · {probe.format || "—"}
          </dd>
          {probe.width > 0 && (
            <>
              <dt>{t("mediaDimensions")}</dt>
              <dd>
                {probe.width} × {probe.height}
              </dd>
              <dt>{t("mediaFrameRate")}</dt>
              <dd>{probe.frame_rate.toFixed(3)}</dd>
              <dt>{t("mediaRotation")}</dt>
              <dd>{t("mediaDegrees", { value: probe.rotation })}</dd>
            </>
          )}
          <dt>{t("mediaAudioTracks")}</dt>
          <dd>{probe.audio_tracks}</dd>
          {probe.sample_rate > 0 && (
            <>
              <dt>{t("mediaSampleRate")}</dt>
              <dd>{t("mediaHertz", { value: probe.sample_rate })}</dd>
              <dt>{t("mediaChannels")}</dt>
              <dd>{probe.channels}</dd>
            </>
          )}
        </dl>
      ) : (
        <p className="muted">{t("mediaNotMeasured")}</p>
      )}
      {media?.source_file_id && (
        <>
          <h3>{t("mediaSourceRange")}</h3>
          <p>
            <a
              href={objectHref({
                kind: "file",
                id: media.source_asset_id ?? media.source_file_id,
                datasetId: target.datasetId ?? data.dataset?.id,
                tab: "facts",
              })}
            >
              {t("mediaSourceRecording")}
            </a>
            {" · "}
            {range(media.source_start_ms, media.source_end_ms)}
          </p>
        </>
      )}
      {alignment && (
        <>
          <h3>{t("mediaAlignment")}</h3>
          <p>
            {alignment.aligned && alignment.offset_ms != null
              ? t("mediaOffset", { value: alignment.offset_ms })
              : t("mediaUnalignable")}
            {" · "}
            {t("mediaConfidence", {
              value: (alignment.confidence * 100).toFixed(1),
            })}
          </p>
          <p className="muted">{t("mediaOffsetMeaning")}</p>
        </>
      )}
      {media && (
        <>
          <h3>{t("mediaIssues")}</h3>
          {issues.length ? (
            <ul className="object-source-list">
              {issues.map((issue, index) => {
                const label = issueLabels[issue.code];
                return (
                  <li key={`${issue.code}:${String(index)}`}>
                    {label ? t(label) : issue.code}
                    {" · "}
                    {range(issue.start_ms, issue.end_ms)}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="muted">{t("mediaNoIssues")}</p>
          )}
        </>
      )}
      <h3>{t("mediaClips", { count: clips.length })}</h3>
      {clips.length ? (
        <ul className="object-source-list">
          {clips.map(({ file: clip, versionId }) => (
            <li key={clip.id}>
              <a
                href={objectHref({
                  kind: "file",
                  id: clip.id,
                  versionId,
                  datasetId: target.datasetId ?? data.dataset?.id,
                  tab: "facts",
                })}
              >
                {clip.filename}
              </a>
              {" · "}
              {range(
                clip.media?.source_start_ms ?? 0,
                clip.media?.source_end_ms,
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t("mediaNoClips")}</p>
      )}
      {history.length > 0 && (
        <details>
          <summary>{t("mediaProcessing")}</summary>
          <ol className="object-source-list">
            {history.map((step, index) => (
              <li key={`${step.operator}:${String(index)}`}>
                {step.operator}
                {" · "}
                {step.version}
                {" · "}
                {range(step.start_ms, step.end_ms)}
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
