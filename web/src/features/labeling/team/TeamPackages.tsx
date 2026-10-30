import { useEffect, useState } from "react";

import { readProduction } from "../../../api/production";
import { useI18n } from "../../../i18n/useI18n";

import { PackageAcceptanceDialog } from "./PackageAcceptanceDialog";

import type {
  PackageAcceptance,
  ProjectWorkbench,
} from "../../../api/production";

const statusKeys = {
  in_progress: "wbPackageInProgress",
  ready: "wbPackageReady",
  accepted: "wbPackageAccepted",
  rejected: "wbPackageRejected",
} as const;

/** Each package's acceptance state and sampling result, read from `package_acceptance`. */
export function TeamPackages({
  data,
  canAccept,
  onChanged,
}: {
  data: ProjectWorkbench;
  canAccept: boolean;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [rows, setRows] = useState<PackageAcceptance[]>([]);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const projectId = data.project.id;
  useEffect(() => {
    let live = true;
    void Promise.all(
      data.packages.map((item) =>
        readProduction<PackageAcceptance>("package_acceptance", {
          project_id: projectId,
          package_id: item.id,
        }),
      ),
    ).then(
      (values) => {
        if (live) setRows(values);
      },
      (reason: unknown) => {
        if (live)
          setError(reason instanceof Error ? reason.message : String(reason));
      },
    );
    return () => {
      live = false;
    };
  }, [data, projectId]);
  const name = (id: string) =>
    data.packages.find((item) => item.id === id)?.name ?? id;
  const selected = rows.find((row) => row.package_id === open);
  return (
    <section className="card wb-team-packages">
      <h2>{t("wbPackageAcceptance")}</h2>
      <div className="table-wrap">
        <table aria-label={t("wbPackageAcceptance")}>
          <thead>
            <tr>
              <th>{t("wbPackage")}</th>
              <th>{t("wbStatus")}</th>
              <th>{t("wbApprovedOfTotal")}</th>
              <th>{t("wbSamplingRule")}</th>
              <th>{t("wbLatestInspection")}</th>
              {canAccept && <th>{t("wbActions")}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.package_id} data-package-id={row.package_id}>
                <td>{name(row.package_id)}</td>
                <td data-status={row.status}>{t(statusKeys[row.status])}</td>
                <td>{`${String(row.approved)} / ${String(row.total)}`}</td>
                <td>
                  {row.sampling
                    ? t("wbSamplingSummary", {
                        sample: row.sampling.sample_size,
                        allowed: row.sampling.acceptance_number,
                      })
                    : t("wbSamplingPending")}
                </td>
                <td>
                  {!row.latest
                    ? t("wbNoInspection")
                    : row.latest.accepted
                      ? t("wbInspectionAccepted", {
                          defective: row.latest.defective_count,
                          sample: row.latest.sampling.sample_size,
                        })
                      : t("wbInspectionRejected", {
                          defective: row.latest.defective_count,
                          sample: row.latest.sampling.sample_size,
                          returned: row.latest.returned_task_ids.length,
                        })}
                </td>
                {canAccept && (
                  <td>
                    {row.status === "ready" && row.sampling && (
                      <button
                        type="button"
                        onClick={() => {
                          setOpen(row.package_id);
                        }}
                      >
                        {t("wbAcceptPackage")}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      {selected?.sampling && (
        <PackageAcceptanceDialog
          key={selected.package_id}
          projectId={projectId}
          packageName={name(selected.package_id)}
          acceptance={selected}
          sampling={selected.sampling}
          onCancel={() => {
            setOpen(null);
          }}
          onDone={() => {
            setOpen(null);
            onChanged();
          }}
        />
      )}
    </section>
  );
}
