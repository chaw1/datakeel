import { useEffect, useRef, useState } from "react";
import { Group, Image as CanvasImage, Layer, Rect, Stage } from "react-konva";

import { useI18n } from "../../../i18n/useI18n";
import { altKeyName } from "../platformKeys";

import { CanvasControls } from "./CanvasControls";
import { CanvasScaleContext, CanvasViewContext } from "./editorContext";
import { arrowDelta, clamp } from "./geometry";
import { useCanvasTokens } from "./useCanvasTokens";
import { useImageSource } from "./useImageSource";

import type { Point } from "./types";
import type { KonvaEventObject } from "konva/lib/Node";
import type { ReactNode } from "react";

interface CanvasProps {
  width: number;
  height: number;
  mediaUrl?: string;
  thumbnailUrl?: string;
  children: ReactNode;
  /** Editor controls shown in the single row above the canvas. */
  toolbar?: ReactNode;
  /** While drawing, existing annotations ignore the pointer so every press adds a point. */
  drawing?: boolean;
  onStart?: (point: Point) => void;
  onMove?: (point: Point) => void;
  onFinish?: (point: Point) => void;
}
export function ImageCanvas({
  width,
  height,
  mediaUrl,
  thumbnailUrl,
  children,
  toolbar,
  drawing = false,
  onStart,
  onMove,
  onFinish,
}: CanvasProps) {
  const { t } = useI18n();
  const tokens = useCanvasTokens();
  const container = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ width: 720, height: 480 });
  const [view, setView] = useState({ zoom: 1, x: 0, y: 0 });
  const [pan, setPan] = useState(false);
  const { image, failed, loading } = useImageSource(mediaUrl, thumbnailUrl);
  useEffect(() => {
    const node = container.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries.at(0);
      if (entry && entry.contentRect.width > 0) {
        setViewport({
          width: Math.round(entry.contentRect.width),
          height: Math.max(240, Math.round(entry.contentRect.height)),
        });
      }
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, []);
  const fit = Math.min(viewport.width / width, viewport.height / height);
  const scale = fit * view.zoom;
  const center = {
    x: (viewport.width - width * fit) / 2,
    y: (viewport.height - height * fit) / 2,
  };
  // The image area on screen, so label chips can stay inside it while zoomed in.
  const origin = { x: center.x + view.x, y: center.y + view.y };
  const visible = {
    x1: -origin.x / scale,
    y1: -origin.y / scale,
    x2: (viewport.width - origin.x) / scale,
    y2: (viewport.height - origin.y) / scale,
  };
  function position(
    event: KonvaEventObject<MouseEvent | TouchEvent>,
  ): Point | null {
    const pointer = event.target.getStage()?.getPointerPosition();
    return pointer
      ? {
          x: clamp((pointer.x - center.x - view.x) / scale, width),
          y: clamp((pointer.y - center.y - view.y) / scale, height),
        }
      : null;
  }
  function pointEvent(
    event: KonvaEventObject<MouseEvent | TouchEvent>,
    callback?: (p: Point) => void,
    backgroundOnly = false,
  ) {
    if (
      pan ||
      (backgroundOnly &&
        event.target !== event.target.getStage() &&
        event.target.name() !== "wb-canvas-background")
    )
      return;
    const point = position(event);
    if (point) callback?.(point);
  }
  function zoomBy(
    factor: number,
    origin: Point = { x: viewport.width / 2, y: viewport.height / 2 },
  ) {
    setView((current) => {
      const zoom = Math.max(0.1, Math.min(20, current.zoom * factor));
      const ratio = zoom / current.zoom;
      return {
        zoom,
        x: origin.x - center.x - (origin.x - center.x - current.x) * ratio,
        y: origin.y - center.y - (origin.y - center.y - current.y) * ratio,
      };
    });
  }
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    node.tabIndex = 0;
    function keydown(event: KeyboardEvent) {
      if (event.ctrlKey || event.metaKey || event.isComposing) return;
      const delta = arrowDelta(event.key, 30);
      if (event.altKey && delta) {
        event.preventDefault();
        event.stopPropagation();
        setView((current) => ({
          ...current,
          x: current.x + delta.x,
          y: current.y + delta.y,
        }));
      } else if (["+", "=", "-", "0"].includes(event.key)) {
        event.preventDefault();
        event.stopPropagation();
        if (event.key === "0") setView({ zoom: 1, x: 0, y: 0 });
        else zoomBy(event.key === "-" ? 0.8 : 1.25);
      }
    }
    node.addEventListener("keydown", keydown);
    return () => {
      node.removeEventListener("keydown", keydown);
    };
  });
  return (
    <div className="wb-image-editor">
      <div className="wb-tool-rail">
        <div className="wb-editor-toolbar">{toolbar}</div>
        <CanvasControls
          pan={pan}
          status={t("wbEditorImageStatus", {
            width,
            height,
            zoom: Math.round(scale * 100),
          })}
          onZoom={(factor) => {
            zoomBy(factor);
          }}
          onFit={() => {
            setView({ zoom: 1, x: 0, y: 0 });
          }}
          onPan={() => {
            setPan(!pan);
          }}
        />
        <p className="muted wb-rail-hint">
          {t("wbEditorPanHint", { alt: altKeyName() })}
        </p>
      </div>
      <div
        ref={container}
        className="wb-canvas"
        role="application"
        aria-label={t("wbEditorCanvas")}
      >
        <div className="wb-canvas-stage">
          <Stage
            width={viewport.width}
            height={viewport.height}
            onMouseDown={(event) => {
              container.current?.focus({ preventScroll: true });
              pointEvent(event, onStart, true);
            }}
            onMouseMove={(event) => {
              pointEvent(event, onMove);
            }}
            onMouseUp={(event) => {
              pointEvent(event, onFinish);
            }}
            onTouchStart={(event) => {
              container.current?.focus({ preventScroll: true });
              pointEvent(event, onStart, true);
            }}
            onTouchMove={(event) => {
              pointEvent(event, onMove);
            }}
            onTouchEnd={(event) => {
              pointEvent(event, onFinish);
            }}
            onWheel={(event) => {
              event.evt.preventDefault();
              zoomBy(
                event.evt.deltaY > 0 ? 0.9 : 1.1,
                event.target.getStage()?.getPointerPosition() ?? undefined,
              );
            }}
          >
            <Layer>
              <Group
                x={center.x + view.x}
                y={center.y + view.y}
                scaleX={scale}
                scaleY={scale}
                draggable={pan}
                onDragEnd={(event) => {
                  if (event.target !== event.currentTarget) return;
                  setView((current) => ({
                    ...current,
                    x: event.target.x() - center.x,
                    y: event.target.y() - center.y,
                  }));
                }}
              >
                <Rect
                  name="wb-canvas-background"
                  width={width}
                  height={height}
                  fill={tokens.background}
                />
                {image && (
                  <CanvasImage
                    image={image}
                    width={width}
                    height={height}
                    listening={false}
                  />
                )}
                <CanvasScaleContext value={scale}>
                  <CanvasViewContext value={visible}>
                    <Group listening={!pan && !drawing}>{children}</Group>
                  </CanvasViewContext>
                </CanvasScaleContext>
              </Group>
            </Layer>
          </Stage>
        </div>
        <div className="wb-canvas-notes">
          {failed ? (
            <p role="alert">{t("wbEditorImageError")}</p>
          ) : loading ? (
            <p role="status">{t("wbEditorLoading")}</p>
          ) : null}
          {!mediaUrl && <p>{t("wbEditorNoImage")}</p>}
        </div>
      </div>
    </div>
  );
}
