import { useI18n } from "../../i18n/useI18n";

import { altKeyName } from "./platformKeys";

import type { useAnnotationSession } from "./session/useAnnotationSession";

export function TaskToolbar({
  editable,
  busy,
  personal,
  session,
  onNavigate,
  navigation,
  notice,
  onSubmit,
  help,
  setHelp,
}: {
  editable: boolean;
  busy: boolean;
  personal: boolean;
  session: ReturnType<typeof useAnnotationSession>;
  onNavigate: (direction: -1 | 0 | 1) => void;
  navigation: { previous: boolean; next: boolean };
  notice: string;
  onSubmit: () => void;
  help: boolean;
  setHelp: (value: boolean) => void;
}) {
  const { t } = useI18n();
  const { flush } = session;
  return (
    <>
      <div className="wb-toolbar">
        <button
          type="button"
          onClick={() => {
            onNavigate(0);
          }}
        >
          {t("wbBack")}
        </button>
        <button
          type="button"
          disabled={!navigation.previous}
          onClick={() => {
            onNavigate(-1);
          }}
        >
          {t("wbPrevious")}
        </button>
        <button
          type="button"
          disabled={!navigation.next}
          onClick={() => {
            onNavigate(1);
          }}
        >
          {t("wbNext")}
        </button>
        {editable && (
          <>
            <button
              type="button"
              disabled={!session.canUndo || busy}
              onClick={session.undo}
            >
              {t("wbUndo")}
            </button>
            <button
              type="button"
              disabled={!session.canRedo || busy}
              onClick={session.redo}
            >
              {t("wbRedo")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                void flush();
              }}
            >
              {t("wbSave")}
            </button>
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={() => {
                onSubmit();
              }}
            >
              {t(personal ? "wbSubmitPersonal" : "wbSubmit")}
            </button>
          </>
        )}
        <button
          type="button"
          aria-expanded={help}
          aria-label={t("wbShortcuts")}
          title={t("wbShortcuts")}
          onClick={() => {
            setHelp(!help);
          }}
        >
          {t("wbShortcutsShort")}
        </button>
        <span role="status" className="wb-nav-notice">
          {notice}
        </span>
      </div>
      {help && (
        <section className="card wb-shortcuts" aria-label={t("wbShortcuts")}>
          <h2>{t("wbShortcuts")}</h2>
          <p>{t("wbCommonKeys", { alt: altKeyName() })}</p>
          <p>{t("wbEditorKeys")}</p>
          <button
            type="button"
            onClick={() => {
              setHelp(false);
            }}
          >
            {t("wbClose")}
          </button>
        </section>
      )}
    </>
  );
}
