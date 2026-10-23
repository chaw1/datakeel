import { useEffect, useRef, useState } from "react";

import { get } from "../api/client";
import { kindLabels } from "../features/object/descriptors";
import { objectHref } from "../features/object/navigation";
import { localizedObjectName } from "../i18n/graphCatalogNames";
import { useI18n } from "../i18n/useI18n";
import { useCompositionGuard } from "../lib/useCompositionGuard";
import { useResource } from "../lib/useResource";

import { Icon } from "./Icon";
import { ResourceState } from "./ResourceState";
import "./command-palette.css";

import type { components } from "../api/generated";
import type { KeyboardEvent } from "react";

type SearchResult = components["schemas"]["SearchResult"];
const identity =
  /^(?:[\da-f]{8}|[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12})$/i;

export function CommandPalette({
  onNavigate,
}: {
  onNavigate?: (href: string) => void;
}) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const modal = useRef<HTMLDialogElement>(null);
  const pasteRevision = useRef(0);
  const isComposing = useCompositionGuard();
  const resource = useResource<SearchResult[]>(
    open
      ? `/api/search?${new URLSearchParams({ q: query, limit: "40" })}`
      : null,
  );
  const items = resource.value ?? [];
  const index = Math.min(chosen, Math.max(0, items.length - 1));
  const selected = items.at(index);

  function navigate(href: string) {
    if (isComposing()) return;
    setOpen(false);
    setQuery("");
    setChosen(0);
    pasteRevision.current++;
    if (onNavigate) onNavigate(href);
    else window.location.hash = href;
  }
  function openObject(item: SearchResult) {
    navigate(
      objectHref({
        kind: item.kind,
        id: item.id,
        datasetId: item.dataset_id ?? undefined,
        versionId: item.version_id ?? undefined,
        tab: "relations",
      }),
    );
  }
  function startConversation(item: SearchResult) {
    const prompt = t("cmdPrompt", {
      name: localizedObjectName(item.kind, item.name, locale),
      kind: t(kindLabels[item.kind]),
      id: item.id,
    });
    navigate(
      `#/agent?${new URLSearchParams({ prompt, ...(item.dataset_id ? { dataset: item.dataset_id } : {}) })}`,
    );
  }
  useEffect(() => {
    const key = (event: globalThis.KeyboardEvent) => {
      if (isComposing(event)) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
      }
    };
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("keydown", key);
    };
  }, [isComposing]);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    const pendingPaste = pasteRevision;
    input.current?.focus();
    return () => {
      pendingPaste.current++;
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, [open]);
  function listKey(event: KeyboardEvent<HTMLInputElement>) {
    if (isComposing(event.nativeEvent)) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const offset = event.key === "ArrowDown" ? 1 : -1;
      const next = (index + offset + items.length) % Math.max(items.length, 1);
      setChosen(next);
      document
        .getElementById(`command-option-${String(next)}`)
        ?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && selected) {
      event.preventDefault();
      openObject(selected);
    }
  }
  function dialogKey(event: KeyboardEvent<HTMLElement>) {
    if (isComposing(event.nativeEvent)) return;
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
    if (event.key === "Tab") {
      const nodes = modal.current?.querySelectorAll<HTMLElement>(
        'input,button:not([tabindex="-1"])',
      );
      const first = nodes?.[0];
      const last = nodes?.[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  }
  async function paste(value: string) {
    setQuery(value);
    setChosen(0);
    const revision = ++pasteRevision.current;
    if (!identity.test(value) || isComposing()) return;
    try {
      const results = await get<SearchResult[]>(
        `/api/search?${new URLSearchParams({ q: value, limit: "100" })}`,
      );
      const matches = results.filter((item) =>
        item.id.toLowerCase().startsWith(value.toLowerCase()),
      );
      if (
        revision === pasteRevision.current &&
        matches.length === 1 &&
        !isComposing()
      )
        openObject(matches[0]);
    } catch {
      /* The normal search response provides a retry action. */
    }
  }
  return (
    <>
      <button
        className="command-trigger"
        aria-label={t("cmdOpen")}
        onClick={() => {
          if (!isComposing()) setOpen(true);
        }}
      >
        <Icon name="search" size={15} />
        <span>{t("cmdOpen")}</span>
        <kbd>{t("cmdShortcut")}</kbd>
      </button>
      {open && (
        <div className="command-overlay">
          <button
            className="command-backdrop"
            tabIndex={-1}
            aria-label={t("cmdClose")}
            onClick={() => {
              if (!isComposing()) setOpen(false);
            }}
          />
          <dialog
            open
            tabIndex={-1}
            className="command-dialog"
            aria-modal="true"
            aria-labelledby="command-title"
            ref={modal}
            onKeyDown={dialogKey}
          >
            <header>
              <h2 id="command-title">{t("cmdTitle")}</h2>
              <button
                className="icon-button"
                aria-label={t("cmdClose")}
                onClick={() => {
                  if (!isComposing()) setOpen(false);
                }}
              >
                <Icon name="close" />
              </button>
            </header>
            <input
              ref={input}
              role="combobox"
              aria-label={t("cmdSearch")}
              aria-expanded="true"
              aria-controls="command-options"
              aria-activedescendant={
                selected ? `command-option-${String(index)}` : undefined
              }
              autoComplete="off"
              maxLength={200}
              value={query}
              placeholder={t("cmdPlaceholder")}
              onKeyDown={listKey}
              onChange={(event) => {
                pasteRevision.current++;
                setQuery(event.target.value);
                setChosen(0);
              }}
              onPaste={(event) => {
                if (isComposing()) return;
                const value = event.clipboardData.getData("text").trim();
                if (!identity.test(value)) return;
                event.preventDefault();
                void paste(value);
              }}
            />
            <ResourceState
              loading={resource.loading}
              error={resource.error}
              onRetry={resource.reload}
            />
            <ul id="command-options" role="listbox" aria-label={t("cmdTitle")}>
              {items.map((item, position) => (
                <li key={`${item.kind}:${item.id}`} role="presentation">
                  <button
                    id={`command-option-${String(position)}`}
                    role="option"
                    aria-selected={position === index}
                    tabIndex={-1}
                    onMouseEnter={() => {
                      setChosen(position);
                    }}
                    onClick={() => {
                      openObject(item);
                    }}
                  >
                    <span className="command-kind">
                      {t(kindLabels[item.kind])}
                    </span>
                    <span className="command-name">
                      {localizedObjectName(item.kind, item.name, locale)}
                    </span>
                    <code title={item.id}>{item.id.slice(0, 8)}</code>
                  </button>
                </li>
              ))}
            </ul>
            {!resource.loading && !items.length && (
              <p className="empty-state">{t("cmdEmpty")}</p>
            )}
            <footer>
              {selected && (
                <button
                  className="text-button command-chat"
                  onClick={() => {
                    startConversation(selected);
                  }}
                >
                  {t("cmdConversation", {
                    name: localizedObjectName(
                      selected.kind,
                      selected.name,
                      locale,
                    ),
                  })}
                </button>
              )}
              <p>{t("cmdHint")}</p>
            </footer>
          </dialog>
        </div>
      )}
    </>
  );
}
