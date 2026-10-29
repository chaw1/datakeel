import { useEffect, useState } from "react";

interface LoadedImage {
  source: string;
  image: HTMLImageElement;
  owner?: string;
}
/** Show a usable preview before requesting its full-resolution replacement. */
export function useImageSource(source?: string, thumbnail?: string) {
  const [full, setFull] = useState<LoadedImage | null>(null);
  const [preview, setPreview] = useState<LoadedImage | null>(null);
  const [failedSource, setFailedSource] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const retry = () => {
      setAttempt((value) => value + 1);
    };
    window.addEventListener("online", retry);
    return () => {
      window.removeEventListener("online", retry);
    };
  }, []);
  useEffect(() => {
    if (!source && !thumbnail) return;
    let active = true;
    const images: HTMLImageElement[] = [];
    function loadFull() {
      if (!source || !active) return;
      const image = new Image();
      images.push(image);
      image.decoding = "async";
      image.onload = () => {
        if (active) setFull({ source, image });
      };
      image.onerror = () => {
        if (active) setFailedSource(source);
      };
      image.src = source;
    }
    if (thumbnail && thumbnail !== source) {
      const image = new Image();
      images.push(image);
      image.decoding = "async";
      image.onload = () => {
        if (!active) return;
        setPreview({ source: thumbnail, owner: source, image });
        loadFull();
      };
      image.onerror = loadFull;
      image.src = thumbnail;
    } else loadFull();
    return () => {
      active = false;
      for (const image of images) {
        image.onload = null;
        image.onerror = null;
      }
    };
  }, [source, thumbnail, attempt]);
  const image =
    full && full.source === source
      ? full.image
      : preview && preview.source === thumbnail && preview.owner === source
        ? preview.image
        : undefined;
  return {
    image,
    failed: Boolean(
      source && failedSource === source && full?.source !== source,
    ),
    loading: Boolean(source && full?.source !== source),
  };
}
