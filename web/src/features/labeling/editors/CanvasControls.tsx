import { useI18n } from "../../../i18n/useI18n";

/** Zoom and pan controls floating over the canvas corner so they take no layout height. */
export function CanvasControls({
  pan,
  status,
  onZoom,
  onFit,
  onPan,
}: {
  pan: boolean;
  status: string;
  onZoom: (factor: number) => void;
  onFit: () => void;
  onPan: () => void;
}) {
  const { t } = useI18n();
  return (
    <div
      className="wb-canvas-controls"
      role="group"
      aria-label={t("wbEditorView")}
    >
      <button
        type="button"
        onClick={() => {
          onZoom(1.25);
        }}
      >
        {t("wbEditorZoomIn")}
      </button>
      <button
        type="button"
        onClick={() => {
          onZoom(0.8);
        }}
      >
        {t("wbEditorZoomOut")}
      </button>
      <button type="button" onClick={onFit}>
        {t("wbEditorFit")}
      </button>
      <button type="button" aria-pressed={pan} onClick={onPan}>
        {t("wbEditorPan")}
      </button>
      <output>{status}</output>
    </div>
  );
}
