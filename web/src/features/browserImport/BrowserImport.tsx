import { useRef, useState } from "react";

import { uploadFolder } from "../../api/uploads";
import { Button, Input, Surface } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { prepareFolderUpload, previewFolder } from "./folder";
import { FolderPreview } from "./FolderPreview";

import "./browserImport.css";

import type { FolderSelection } from "./folder";
import type { FolderUpload } from "../../api/uploads";
import type { SubmitEvent } from "react";

const folderMode = { webkitdirectory: "" };

export function BrowserImport({
  onDone,
  onCancel,
}: {
  onDone: (datasetId: string) => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [name, setName] = useState("");
  const [selection, setSelection] = useState<FolderSelection>();
  const [scanning, setScanning] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const [skipUnreadable, setSkipUnreadable] = useState(true);
  const prepared = useRef<FolderUpload>(undefined);
  const omitted =
    selection?.images.filter((image) => !image.readable).length ?? 0;
  const images =
    selection?.images.filter((image) => image.readable || !skipUnreadable) ??
    [];

  function formError(reason: unknown) {
    const message = reason instanceof Error ? reason.message : "";
    switch (message) {
      case "importNoImages":
      case "importPathError":
      case "importSizeLimit":
        return t(message);
      default:
        return message || t("importFailed");
    }
  }

  async function preview(files: File[]) {
    if (scanning || submitting || !files.length) return;
    setSelection(undefined);
    setScanning(true);
    setError("");
    setSkipUnreadable(true);
    prepared.current = undefined;
    try {
      const next = await previewFolder(files);
      setSelection(next);
      setName(next.name.slice(0, 200));
    } catch (reason) {
      setError(formError(reason));
    } finally {
      setScanning(false);
    }
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (
      !selection ||
      !images.length ||
      !name.trim() ||
      submitting ||
      isComposing()
    )
      return;
    setSubmitting(true);
    setProgress(0);
    setError("");
    try {
      const upload =
        prepared.current ??
        (await prepareFolderUpload(selection, images, name.trim()));
      prepared.current = upload;
      onDone(await uploadFolder(upload, setProgress));
    } catch (reason) {
      setError(formError(reason));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Surface
      as="section"
      className="browser-import"
      aria-labelledby="browser-import-title"
    >
      <header className="browser-import-header">
        <div>
          <h2 id="browser-import-title">{t("importImages")}</h2>
          <p className="muted">{t("importFolderHint")}</p>
        </div>
        <Button
          disabled={submitting || scanning}
          variant="ghost"
          onClick={onCancel}
        >
          {t("importCancel")}
        </Button>
      </header>
      <form
        aria-busy={submitting || scanning}
        className="browser-import-form"
        onSubmit={(event) => void submit(event)}
      >
        <div className="import-fields">
          <label>
            {t("importChooseFolder")}
            <input
              type="file"
              {...folderMode}
              multiple
              disabled={submitting || scanning}
              onChange={(event) => {
                void preview(Array.from(event.currentTarget.files ?? []));
              }}
            />
          </label>
          <label>
            {t("importDatasetName")}
            <Input
              required
              maxLength={200}
              value={name}
              disabled={submitting || scanning}
              onChange={(event) => {
                prepared.current = undefined;
                setName(event.target.value);
              }}
            />
          </label>
        </div>
        {scanning && <p role="status">{t("importScanning")}</p>}
        {selection && <FolderPreview selection={selection} />}
        {omitted > 0 && (
          <label className="import-skip-control">
            <input
              type="checkbox"
              checked={skipUnreadable}
              disabled={submitting}
              onChange={(event) => {
                prepared.current = undefined;
                setSkipUnreadable(event.target.checked);
              }}
            />
            {t("importSkipUnreadable", { count: omitted })}
          </label>
        )}
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        {submitting && (
          <div className="import-progress">
            <progress
              value={progress}
              max={100}
              aria-label={t("importProgress")}
            />
            <span role="status">
              {t(progress === 100 ? "importPublishing" : "importUploading", {
                percent: progress,
              })}
            </span>
          </div>
        )}
        <div className="import-footer">
          <Button
            type="submit"
            variant="primary"
            disabled={scanning || submitting || !name.trim() || !images.length}
          >
            {t("importDataset")}
          </Button>
        </div>
      </form>
    </Surface>
  );
}
