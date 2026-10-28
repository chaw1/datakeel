import { useState } from "react";

import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { bytes } from "../../lib/format";
import { useResource } from "../../lib/useResource";

import { VersionSummary } from "./VersionSummary";

import type { components } from "../../api/generated";
import type { Version } from "../../api/types";
import type { MessageKey } from "../../i18n/en";
import type { SubmitEvent } from "react";

type Diff = components["schemas"]["VersionDiff"];
type Category = Diff["files"][number]["category"];
const categories: Record<Category, MessageKey> = {
  added: "versionAdded",
  removed: "versionRemoved",
  content_changed: "versionContentChanged",
  metadata_changed: "versionMetadataChanged",
  unchanged: "versionUnchanged",
};

export function VersionCompare({
  versions,
  datasetId,
}: {
  versions: Version[];
  datasetId: string;
}) {
  const { t } = useI18n();
  const [before, setBefore] = useState(versions.at(-1)?.id ?? "");
  const [after, setAfter] = useState(versions[0]?.id ?? "");
  const [pair, setPair] = useState<{ before: string; after: string } | null>(
    null,
  );
  const [category, setCategory] = useState<Category>("added");
  const [offset, setOffset] = useState(0);
  const path = pair
    ? `/api/datasets/${encodeURIComponent(datasetId)}/diff?${new URLSearchParams({ ...pair, category, offset: String(offset), limit: "50" }).toString()}`
    : null;
  const diff = useResource<Diff>(path);
  function compare(event: SubmitEvent) {
    event.preventDefault();
    setPair({ before, after });
    setOffset(0);
  }
  return (
    <section className="version-compare" aria-label={t("versionCompare")}>
      <h3>{t("versionCompare")}</h3>
      <p className="muted">{t("versionCompareHint")}</p>
      <form className="version-controls" onSubmit={compare}>
        <label>
          {t("versionBefore")}
          <select
            aria-label={t("versionBefore")}
            value={before}
            onBlur={(e) => {
              setBefore(e.target.value);
            }}
            onChange={(e) => {
              setBefore(e.target.value);
            }}
          >
            {versions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("versionAfter")}
          <select
            aria-label={t("versionAfter")}
            value={after}
            onBlur={(e) => {
              setAfter(e.target.value);
            }}
            onChange={(e) => {
              setAfter(e.target.value);
            }}
          >
            {versions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id}
              </option>
            ))}
          </select>
        </label>
        <button
          className="button"
          type="submit"
          disabled={
            versions.length < 2 || !before || !after || before === after
          }
        >
          {t("versionCompare")}
        </button>
      </form>
      {versions.length < 2 && <p>{t("versionNeedTwo")}</p>}
      <ResourceState {...diff} onRetry={diff.reload} />
      {diff.value && (
        <>
          <div className="version-categories" aria-label={t("versionChanges")}>
            {Object.entries(categories).map(([key, label]) => (
              <button
                key={key}
                type="button"
                className="button subtle"
                aria-pressed={category === key}
                onClick={() => {
                  setCategory(key as Category);
                  setOffset(0);
                }}
              >
                {t(label)} · {diff.value?.counts[key as Category]}
              </button>
            ))}
          </div>
          <VersionSummary
            before={diff.value.before_summary}
            after={diff.value.after_summary}
          />
          <div className="table-scroll">
            <table>
              <caption>{t(categories[category])}</caption>
              <thead>
                <tr>
                  <th>{t("fileName")}</th>
                  <th>{t("versionBefore")}</th>
                  <th>{t("versionAfter")}</th>
                </tr>
              </thead>
              <tbody>
                {diff.value.files.map((item) => (
                  <tr key={item.file_id}>
                    <td>{item.after?.filename ?? item.before?.filename}</td>
                    {[item.before, item.after].map((file, index) => (
                      <td key={index}>
                        {file ? (
                          <>
                            {bytes(file.size)}{" "}
                            <code title={file.sha256}>
                              {file.sha256.slice(0, 12)}
                            </code>
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!diff.value.files.length && <p>{t("versionNoChanges")}</p>}
          <div className="version-controls">
            <button
              className="button subtle"
              disabled={offset === 0 || diff.loading}
              onClick={() => {
                setOffset(Math.max(0, offset - 50));
              }}
            >
              {t("previous")}
            </button>
            <span>{t("versionOffset", { offset: offset + 1 })}</span>
            <button
              className="button subtle"
              disabled={diff.value.next_offset === null || diff.loading}
              onClick={() => {
                setOffset(diff.value?.next_offset ?? offset);
              }}
            >
              {t("next")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
