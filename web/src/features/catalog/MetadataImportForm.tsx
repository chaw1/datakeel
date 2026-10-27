import { useState } from "react";

import { importAirflow, importDbt } from "../../api/metadataImports";
import { useI18n } from "../../i18n/useI18n";

import type {
  DbtImportRequest,
  MetadataImportReport,
} from "../../api/metadataImports";
import type { MessageKey } from "../../i18n/en";
import type { SyntheticEvent } from "react";

type Artifact = "manifest" | "catalog" | "run_results" | "document";
const labels: Record<Artifact, MessageKey> = {
  manifest: "metadataManifest",
  catalog: "metadataCatalog",
  run_results: "metadataRunResults",
  document: "metadataAirflowFile",
};

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === "string" ? reader.result : "");
    };
    reader.onerror = () => {
      reject(new Error(file.name));
    };
    reader.readAsText(file);
  });
}

export function MetadataImportForm({ onImported }: { onImported: () => void }) {
  const { t } = useI18n();
  const [system, setSystem] = useState("dbt");
  const [source, setSource] = useState("");
  const [name, setName] = useState("");
  const [files, setFiles] = useState<Partial<Record<Artifact, File>>>({});
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<MetadataImportReport | null>(null);
  const artifacts: Artifact[] =
    system === "dbt" ? ["manifest", "catalog", "run_results"] : ["document"];
  async function decode(
    artifact: Artifact,
  ): Promise<DbtImportRequest["manifest"] | undefined> {
    const file = files[artifact];
    if (!file) return undefined;
    let value: unknown;
    try {
      value = JSON.parse(await readFile(file));
    } catch {
      throw new Error(t("metadataInvalidJson", { name: file.name }));
    }
    if (!value || typeof value !== "object" || Array.isArray(value))
      throw new Error(t("metadataInvalidJson", { name: file.name }));
    return value as DbtImportRequest["manifest"];
  }
  async function submit(event: SyntheticEvent) {
    event.preventDefault();
    setPending(true);
    setError("");
    setReport(null);
    try {
      if (system === "dbt") {
        const manifest = await decode("manifest");
        if (!manifest) throw new Error(t("metadataFileRequired"));
        const metadata = manifest.metadata;
        const version: unknown =
          metadata && typeof metadata === "object" && !Array.isArray(metadata)
            ? (metadata as Record<string, unknown>).dbt_schema_version
            : undefined;
        if (
          typeof version !== "string" ||
          !/\/manifest\/v1[012]\.json$/.test(version)
        )
          throw new Error(t("metadataUnsupportedManifest"));
        setReport(
          await importDbt({
            source_id: source.trim(),
            name: name.trim() || "dbt",
            manifest,
            catalog: await decode("catalog"),
            run_results: await decode("run_results"),
          }),
        );
      } else {
        const document = await decode("document");
        if (!document) throw new Error(t("metadataFileRequired"));
        setReport(
          await importAirflow({
            source_id: source.trim(),
            name: name.trim() || "Airflow",
            document,
          }),
        );
      }
      onImported();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="card catalog-detail">
      <h2>{t("metadataImports")}</h2>
      <p>{t("metadataImportHelp")}</p>
      <form
        className="metadata-import-form"
        onSubmit={(event) => {
          void submit(event);
        }}
      >
        <div className="catalog-form-grid">
          <label>
            {t("metadataSystem")}
            <select
              value={system}
              onBlur={(event) => {
                setSystem(event.target.value);
              }}
              disabled={pending}
              onChange={(event) => {
                setSystem(event.target.value);
                setFiles({});
                setReport(null);
                setError("");
              }}
            >
              <option value="dbt">{t("metadataDbt")}</option>
              <option value="airflow">{t("metadataAirflow")}</option>
            </select>
          </label>
          <label>
            {t("metadataSourceId")}
            <input
              value={source}
              required
              pattern={".*\\S.*"}
              disabled={pending}
              onChange={(event) => {
                setSource(event.target.value);
              }}
            />
          </label>
          <label>
            {t("metadataSourceName")}
            <input
              value={name}
              disabled={pending}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </label>
          {artifacts.map((artifact) => (
            <label key={`${system}:${artifact}`}>
              {t(labels[artifact])}
              <input
                type="file"
                accept=".json,application/json"
                disabled={pending}
                aria-required={
                  artifact === "manifest" || artifact === "document"
                }
                onChange={(event) => {
                  setFiles({ ...files, [artifact]: event.target.files?.[0] });
                }}
              />
            </label>
          ))}
        </div>
        <button className="button primary" disabled={pending} type="submit">
          {t(pending ? "metadataImportPending" : "metadataImportSubmit")}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {report && (
        <div className="catalog-success" role="status">
          <p>
            {t("metadataSummary", {
              new: report.new,
              changed: report.changed,
              deleted: report.deleted,
              unchanged: report.unchanged,
              drafts: report.drafts,
            })}
          </p>
          {!!report.parse_failures.length && (
            <ul>
              {report.parse_failures.map((failure) => (
                <li key={`${failure.origin}:${failure.reason}`}>
                  {failure.origin}: {failure.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
