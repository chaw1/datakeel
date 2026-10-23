import { useState } from "react";

import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { bytes, display } from "../../lib/format";
import { objectHref } from "../object/navigation";

import type { FileItem, Version } from "../../api/types";

export function Files({
  files,
  versions,
  datasetId,
  initialVersionId,
}: {
  files: FileItem[];
  versions: Version[];
  datasetId: string;
  initialVersionId?: string;
}) {
  const { t } = useI18n();

  const [query, setQuery] = useState("");
  const [modality, setModality] = useState("all");
  const [versionId, setVersionId] = useState(initialVersionId ?? "source");
  const [page, setPage] = useState(0);
  const versionFiles =
    versionId === "source"
      ? files
      : (versions.find((version) => version.id === versionId)?.manifest ?? []);
  const filtered = versionFiles.filter(
    (file) =>
      file.filename.toLowerCase().includes(query.toLowerCase()) &&
      (modality === "all" || file.modality === modality),
  );
  const pages = Math.max(1, Math.ceil(filtered.length / 25));
  const current = Math.min(page, pages - 1);
  return (
    <>
      <div className="table-toolbar">
        <label className="search-field">
          <Icon name="search" />
          <input
            aria-label={t("searchFiles")}
            placeholder={t("searchFilesLabel")}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
          />
        </label>
        <select
          aria-label={t("selectFileVersion")}
          value={versionId}
          onBlur={(event) => {
            setVersionId(event.target.value);
            setPage(0);
          }}
          onChange={(event) => {
            setVersionId(event.target.value);
            setPage(0);
          }}
        >
          <option value="source">{t("sourceFiles")}</option>
          {versions.map((version, index) => (
            <option key={version.id} value={version.id}>
              {t("version")} {versions.length - index}
              {index === 0 ? t("latest") : ""}
            </option>
          ))}
        </select>
        <select
          aria-label={t("filterModality")}
          value={modality}
          onBlur={(event) => {
            setModality(event.target.value);
            setPage(0);
          }}
          onChange={(event) => {
            setModality(event.target.value);
            setPage(0);
          }}
        >
          <option value="all">{t("allModalities")}</option>
          {Array.from(
            new Set(versionFiles.map((file) => file.modality).filter(Boolean)),
          ).map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <span className="muted small">
          {filtered.length} {t("files", { count: filtered.length })}
        </span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>{t("fileName")}</th>
              <th>{t("modality")}</th>
              <th>{t("size")}</th>
              <th>{t("contentHash")}</th>
              <th>
                <span className="sr-only">{t("download")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(current * 25, current * 25 + 25).map((file) => (
              <tr key={file.id}>
                <td>
                  <span className="file-name">
                    <span
                      className={`file-icon ${file.modality === "image" ? "image-file" : ""}`}
                    >
                      <Icon
                        name={file.modality === "image" ? "image" : "file"}
                        size={16}
                      />
                    </span>
                    <a
                      href={objectHref({
                        kind: "file",
                        id: file.id,
                        datasetId,
                        versionId:
                          versionId === "source" ? undefined : versionId,
                      })}
                    >
                      {file.filename}
                    </a>
                    {file.metadata?.quarantined === true && (
                      <span className="badge amber">{t("quarantined")}</span>
                    )}
                    {file.metadata?.deleted === true && (
                      <span className="badge gray">{t("deletedFile")}</span>
                    )}
                  </span>
                </td>
                <td>
                  <span className="badge gray">
                    {display(file.modality, t("file"))}
                  </span>
                </td>
                <td className="muted">{bytes(file.size)}</td>
                <td>
                  <code title={file.sha256}>
                    {file.sha256.slice(0, 14) || "—"}
                  </code>
                </td>
                <td>
                  {file.metadata?.deleted !== true && (
                    <a
                      className="icon-button"
                      href={`/api/datasets/${encodeURIComponent(datasetId)}/files/${encodeURIComponent(file.id)}/download${versionId === "source" ? "" : `?version=${encodeURIComponent(versionId)}`}`}
                      aria-label={t("downloadFile", {
                        filename: file.filename,
                      })}
                      download
                    >
                      <Icon name="download" size={16} />
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <div className="empty-state">
          <p>{t("noFilesMatchYourSearch")}</p>
        </div>
      )}
      <div className="pagination">
        <span>
          {filtered.length ? current * 25 + 1 : 0}–
          {Math.min((current + 1) * 25, filtered.length)} {t("of")}{" "}
          {filtered.length} {t("files", { count: filtered.length })}{" "}
        </span>
        <div>
          <button
            className="button subtle"
            disabled={current === 0}
            onClick={() => {
              setPage(current - 1);
            }}
          >
            {t("previous")}{" "}
          </button>
          <span>
            {t("page")} {current + 1} {t("of")} {pages}
          </span>
          <button
            className="button subtle"
            disabled={current + 1 === pages}
            onClick={() => {
              setPage(current + 1);
            }}
          >
            {t("next")}{" "}
          </button>
        </div>
      </div>
    </>
  );
}
