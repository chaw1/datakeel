import { useContext } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "../../../i18n/useI18n";

import { DetailsSlotContext } from "./editorContext";

import type { ReactNode } from "react";

/** Show hints, coordinates and attributes in the drawer, keeping the canvas at full height. */
export function EditorDetails({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const slot = useContext(DetailsSlotContext);
  const content = (
    <section
      className="wb-editor-details"
      aria-label={t("wbEditorDetailsOf", { name: label })}
    >
      {children}
    </section>
  );
  return slot ? createPortal(content, slot) : content;
}
