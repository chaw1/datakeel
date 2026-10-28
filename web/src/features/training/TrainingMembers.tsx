import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import type { SplitSet } from "../../api/training";

export function TrainingMembers({ split }: { split: SplitSet }) {
  const { t } = useI18n();
  const [offset, setOffset] = useState(0);
  const members = split.members.slice(offset, offset + 50);
  return (
    <details className="training-members">
      <summary>{t("trainingMembership")}</summary>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("trainingSample")}</th>
              <th scope="col">{t("trainingSet")}</th>
              <th scope="col">{t("trainingClass")}</th>
            </tr>
          </thead>
          <tbody>
            {members.map((member) => (
              <tr key={member.sample_id}>
                <th scope="row">
                  <code>{member.sample_id}</code>
                </th>
                <td>{member.split}</td>
                <td>{member.labels.join(", ") || t("trainingUnlabelled")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="training-controls">
        <button
          className="button subtle"
          disabled={!offset}
          onClick={() => {
            setOffset(Math.max(0, offset - 50));
          }}
        >
          {t("previous")}
        </button>
        <span>
          {t("versionOffset", {
            offset: split.members.length ? offset + 1 : 0,
          })}
        </span>
        <button
          className="button subtle"
          disabled={offset + 50 >= split.members.length}
          onClick={() => {
            setOffset(offset + 50);
          }}
        >
          {t("next")}
        </button>
      </div>
    </details>
  );
}
