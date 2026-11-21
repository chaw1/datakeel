import { useState } from "react";

import { deleteMemory, updateMemory } from "../../api/memory";
import { Badge, Button, EmptyState, Surface } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import type { Dataset, MemoryEntry } from "../../api/types";

export function MemoryList({
  entries,
  datasets,
  onDeleted,
}: {
  entries: MemoryEntry[];
  datasets: Dataset[];
  onDeleted: () => void;
}) {
  const { t, locale } = useI18n();
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(id: string) {
    if (busy || !content.trim()) return;
    setBusy(true);
    setError("");
    try {
      await updateMemory(id, { content: content.trim() });
      setEditing("");
      onDeleted();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    setBusy(true);
    setError("");
    try {
      await deleteMemory(id);
      setSelected("");
      onDeleted();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  if (!entries.length) return <EmptyState card title={t("memoryEmpty")} />;
  return (
    <div className="memory-list">
      {entries.map((entry) => (
        <Surface
          as="article"
          className="memory-card"
          key={entry.id}
          data-memory-id={entry.id}
        >
          <div className="section-heading">
            <Badge>
              {entry.dataset_id
                ? (datasets.find((dataset) => dataset.id === entry.dataset_id)
                    ?.name ?? entry.dataset_id)
                : t("memoryGlobal")}
            </Badge>
            <Button
              variant="link"
              disabled={busy || editing === entry.id}
              onClick={() => {
                setEditing(entry.id);
                setContent(entry.content);
                setSelected("");
                setError("");
              }}
            >
              {t("memoryEdit")}
            </Button>
            <Button
              variant="link"
              disabled={busy || editing === entry.id}
              onClick={() => {
                setSelected(entry.id);
                setEditing("");
                setError("");
              }}
            >
              {t("memoryDelete")}
            </Button>
          </div>
          {editing === entry.id ? (
            <form
              className="memory-form"
              onSubmit={(event) => {
                event.preventDefault();
                void save(entry.id);
              }}
            >
              <label htmlFor={`memory-edit-${entry.id}`}>
                {t("memoryEditContent")}
              </label>
              <textarea
                id={`memory-edit-${entry.id}`}
                value={content}
                required
                maxLength={6000}
                disabled={busy}
                onChange={(event) => {
                  setContent(event.target.value);
                }}
              />
              {error && (
                <p role="alert" className="error-text">
                  {error}
                </p>
              )}
              <Button
                type="submit"
                variant="primary"
                disabled={busy || !content.trim()}
              >
                {t(busy ? "memorySaving" : "memorySave")}
              </Button>
              <Button
                disabled={busy}
                onClick={() => {
                  setEditing("");
                  setError("");
                }}
              >
                {t("memoryCancelEdit")}
              </Button>
            </form>
          ) : (
            <p className="memory-content">{entry.content}</p>
          )}
          <dl className="memory-facts">
            <div>
              <dt>{t("createdAt")}</dt>
              <dd>
                <time dateTime={entry.created_at}>
                  {date(entry.created_at, locale)}
                </time>
              </dd>
            </div>
            <div>
              <dt>{t("memoryStrength")}</dt>
              <dd>
                {entry.current_strength.toLocaleString(locale, {
                  maximumFractionDigits: 2,
                })}
              </dd>
            </div>
            <div>
              <dt>{t("memoryLastUsed")}</dt>
              <dd>
                {entry.last_used_at ? (
                  <time dateTime={entry.last_used_at}>
                    {date(entry.last_used_at, locale)}
                  </time>
                ) : (
                  t("memoryNeverUsed")
                )}
              </dd>
            </div>
          </dl>
          <div className="memory-sources">
            <span>{t("memorySources")}</span>
            {entry.source_conversation_ids?.length ? (
              entry.source_conversation_ids.map((id) => (
                <a
                  key={id}
                  href={`#/agent?conversation=${encodeURIComponent(id)}`}
                >
                  {t("conversationLabel", { id })}
                </a>
              ))
            ) : (
              <span>{t("memoryManual")}</span>
            )}
          </div>
          {selected === entry.id && (
            <section
              className="memory-confirm"
              role="alertdialog"
              aria-modal="false"
              aria-labelledby={`memory-delete-${entry.id}`}
              aria-describedby={`memory-delete-help-${entry.id}`}
            >
              <h3 id={`memory-delete-${entry.id}`}>{t("memoryDeleteTitle")}</h3>
              <p id={`memory-delete-help-${entry.id}`}>
                {t("memoryDeleteExplanation")}
              </p>
              {error && (
                <p role="alert" className="error-text">
                  {error}
                </p>
              )}
              <div>
                <Button
                  disabled={busy}
                  onClick={() => {
                    setSelected("");
                  }}
                >
                  {t("memoryCancelDelete")}
                </Button>
                <Button
                  variant="danger"
                  disabled={busy}
                  onClick={() => {
                    void remove(entry.id);
                  }}
                >
                  {t(busy ? "memoryDeleting" : "memoryConfirmDelete")}
                </Button>
              </div>
            </section>
          )}
        </Surface>
      ))}
    </div>
  );
}
