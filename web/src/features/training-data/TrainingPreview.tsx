import type { TrainingRecord } from "../../api/trainingData";

const placeholders =
  /(\[(?:EMAIL|PHONE|CHINA_ID|BANK_CARD|IP|SECRET|CREDENTIAL_URL)\])/g;

export function TrainingPreview({ record }: { record: TrainingRecord }) {
  const malformed = record.issues.some(
    (issue) => issue.code === "format_error",
  );
  return (
    <pre className="training-preview">
      {malformed ? (
        <mark>{record.preview}</mark>
      ) : (
        record.preview
          .split(placeholders)
          .map((part, index) =>
            part.startsWith("[") &&
            part.endsWith("]") &&
            /^\[(?:EMAIL|PHONE|CHINA_ID|BANK_CARD|IP|SECRET|CREDENTIAL_URL)\]$/.test(
              part,
            ) ? (
              <mark key={index}>{part}</mark>
            ) : (
              <span key={index}>{part}</span>
            ),
          )
      )}
    </pre>
  );
}
