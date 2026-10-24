import { useI18n } from "../../i18n/useI18n";

import {
  knowledgeFocusLabels,
  knowledgeIntentLabels,
  knowledgeKindLabels,
} from "./knowledgeLabels";

import type { KnowledgeIntent, KnowledgeRecognition } from "../../api/ask";

export function KnowledgeRecognitionEvidence({
  recognition,
  intent,
}: {
  recognition: KnowledgeRecognition;
  intent?: KnowledgeIntent;
}) {
  const { t } = useI18n();
  return (
    <div className="knowledge-recognition">
      {recognition.subjects.length ? (
        <ul>
          {recognition.subjects.map(({ text, subject }, index) => (
            <li key={`${subject.asset_ref.asset_id}:${String(index)}`}>
              {t("knowledgeRecognizedSubject", {
                text,
                kind: subject.entity_type
                  ? `${t(knowledgeKindLabels[subject.kind])} · ${subject.entity_type}`
                  : t(knowledgeKindLabels[subject.kind]),
                name: subject.name,
              })}
            </li>
          ))}
        </ul>
      ) : (
        <p>{t("knowledgeRecognizedNoSubject")}</p>
      )}
      <p>
        {recognition.focus_text
          ? t("knowledgeRecognizedFocus", {
              text: recognition.focus_text,
              focus: t(knowledgeFocusLabels[recognition.focus]),
            })
          : t("knowledgeFocusUnknown")}
        {intent && ` → ${t(knowledgeIntentLabels[intent])}`}
      </p>
      {recognition.direction && (
        <p>
          {t("knowledgeRecognizedDirection", {
            direction: t(knowledgeIntentLabels[recognition.direction]),
            text: recognition.direction_text.join(" · "),
          })}
        </p>
      )}
      <p className="ask-muted">
        {t("knowledgeRecognitionRule", { rule: recognition.rule_id })}
      </p>
    </div>
  );
}
