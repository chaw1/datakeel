import { useEffect, useRef, useState } from "react";

/** Native media playback state only; authoritative duration always comes from the server probe. */
export function useMediaPlayback(durationMs: number) {
  const mediaRef = useRef<HTMLMediaElement | null>(null);
  const frameRef = useRef(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const tick = () => {
      const media = mediaRef.current;
      if (media) setCurrentTime(Math.min(durationMs, media.currentTime * 1000));
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frameRef.current);
    };
  }, [playing, durationMs]);

  useEffect(
    () => () => {
      cancelAnimationFrame(frameRef.current);
      mediaRef.current?.pause();
      mediaRef.current = null;
    },
    [],
  );

  function seek(milliseconds: number) {
    const next = Math.max(0, Math.min(milliseconds, durationMs));
    if (mediaRef.current) mediaRef.current.currentTime = next / 1000;
    setCurrentTime(next);
  }
  function toggle() {
    const media = mediaRef.current;
    if (!media) return;
    if (media.paused)
      void media.play().catch(() => {
        setPlaying(false);
      });
    else media.pause();
  }
  return {
    setMedia: (node: HTMLMediaElement | null) => {
      mediaRef.current = node;
    },
    currentTime,
    playing,
    seek,
    toggle,
    setPlaying,
  };
}
