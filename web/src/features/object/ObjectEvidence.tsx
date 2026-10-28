import { lineageHref } from "../../app/lineageNavigation";
import { useI18n } from "../../i18n/useI18n";
import { shortId } from "../../lib/format";
import { ActionReceipt } from "../actions/ActionReceipt";
import { MetricDetails } from "../catalog/MetricDetails";
import { TableDetails } from "../catalog/TableDetails";
import { AssertionChip } from "../evidence/AssertionChip";
import { EvidenceExplorer } from "../evidence/EvidenceExplorer";

import { isObjectKind, objectHref } from "./navigation";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";
import type { LineageTarget } from "../../app/navigation";

export function ObjectEvidence({
  data,
  target,
  reload,
}: {
  data: ObjectData;
  target: ObjectTarget;
  reload: () => void;
}) {
  const { t } = useI18n();
  function receipt(next: LineageTarget) {
    window.location.hash = lineageHref(next);
  }
  if (target.kind === "dataset")
    return (
      <section id="object-section-create-version">
        {target.section === "create-version" && (
          <p className="object-help">{t("objVersionPreparation")}</p>
        )}
        <EvidenceExplorer
          datasetId={target.id}
          onDataChanged={reload}
          onOpenReceipt={receipt}
        />
      </section>
    );
  if (data.table)
    return (
      <section id="object-section-fields">
        <TableDetails tableId={target.id} onOpenReceipt={receipt} />
      </section>
    );
  if (data.metric)
    return (
      <section id="object-section-edit">
        <MetricDetails
          key={`${target.id}:${target.section ?? ""}`}
          metricId={target.id}
          onOpenReceipt={receipt}
          onDataChanged={reload}
          initialEditing={target.section === "edit"}
        />
      </section>
    );
  if (data.action)
    return (
      <section>
        <ActionReceipt run={data.action} onOpenReceipt={receipt} />
        <h2 id="object-section-affected">
          {t("objActionObjects")} · {data.plan?.manifest.objects.length ?? 0}
        </h2>
        <ul className="object-source-list">
          {data.plan?.manifest.objects.map((item) => (
            <li key={item.asset_ref.asset_id}>
              {isObjectKind(item.asset_ref.asset_type) ? (
                <a
                  href={objectHref({
                    kind: item.asset_ref.asset_type,
                    id: item.asset_ref.asset_id,
                    datasetId:
                      data.plan?.manifest.query.dataset_id ?? undefined,
                    tab: "facts",
                  })}
                >
                  {item.asset_ref.asset_type} ·{" "}
                  <code>{shortId(item.asset_ref.asset_id)}</code>
                </a>
              ) : (
                <code>{item.asset_ref.asset_id}</code>
              )}
            </li>
          ))}
        </ul>
      </section>
    );
  return (
    <section className="object-source-evidence">
      <h2>{t("objSourceEvidence")}</h2>
      {!data.samples.some((sample) => sample.assertions.length) && (
        <p className="muted">{t("objNoEvidence")}</p>
      )}
      {data.samples.map((sample) => (
        <article key={`${sample.asset_ref.asset_id}:${sample.source_version}`}>
          <h3>{sample.filename}</h3>
          <div className="assertion-list">
            {[...sample.assertions]
              .sort(
                (a, b) =>
                  Number(b.status === "candidate") -
                  Number(a.status === "candidate"),
              )
              .map((assertion) => (
                <AssertionChip key={assertion.id} assertion={assertion} />
              ))}
          </div>
        </article>
      ))}
    </section>
  );
}
