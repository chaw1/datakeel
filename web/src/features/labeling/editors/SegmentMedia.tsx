/* eslint-disable jsx-a11y/media-has-caption -- Media is the annotation subject, not captioned content. */
import { useState } from "react";

import { useI18n } from "../../../i18n/useI18n";

export function SegmentMedia({
  mediaUrl,
  mediaType,
  setMedia,
  onPlaying,
}: {
  mediaUrl: string;
  mediaType: string;
  setMedia: (node: HTMLMediaElement | null) => void;
  onPlaying: (playing: boolean) => void;
}) {
  const { t } = useI18n();
  const [failedUrl, setFailedUrl] = useState("");
  const events = {
    onPlay: () => {
      onPlaying(true);
    },
    onPause: () => {
      onPlaying(false);
    },
    onEnded: () => {
      onPlaying(false);
    },
    onError: () => {
      setFailedUrl(mediaUrl);
    },
  };
  return (
    <>
      {mediaType.startsWith("video/") ? (
        <video
          ref={setMedia}
          className="wb-segment-video"
          src={mediaUrl}
          controls
          preload="metadata"
          {...events}
        />
      ) : (
        <audio
          ref={setMedia}
          src={mediaUrl}
          controls
          preload="metadata"
          {...events}
        />
      )}
      {failedUrl === mediaUrl && <p role="alert">{t("wbSegmentMediaError")}</p>}
    </>
  );
}
