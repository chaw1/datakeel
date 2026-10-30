import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import type { ProjectWorkbench, TaskWorkbench } from "../../api/production";
import type { ReactNode } from "react";

type DrawerTab = "properties" | "history" | "reviews" | "guide";

export function TaskDrawer({
  task,
  project,
  open = true,
  onToggle,
  detailsRef,
  children,
}: {
  task: TaskWorkbench;
  project: ProjectWorkbench;
  open?: boolean;
  onToggle?: () => void;
  /** Receives the element where editors render the selected annotation's details. */
  detailsRef?: (element: HTMLDivElement | null) => void;
  children?: ReactNode;
}) {
  const { t, locale } = useI18n();
  const [tab, setTab] = useState<DrawerTab>("properties");
  return (
    <aside
      className="wb-drawer"
      aria-label={t("wbDrawer")}
      data-open={open ? "true" : "false"}
    >
      {onToggle && (
        <button
          type="button"
          className="wb-drawer-toggle"
          aria-expanded={open}
          onClick={onToggle}
        >
          {t(open ? "wbCollapseDrawer" : "wbExpandDrawer")}
        </button>
      )}
      <div className="wb-drawer-body" hidden={!open}>
        {children}
        <div className="wb-drawer-tabs" role="group" aria-label={t("wbDrawer")}>
          {(
            [
              ["properties", "wbProperties"],
              ["history", "wbHistory"],
              ["reviews", "wbReviews"],
              ["guide", "wbGuidelines"],
            ] as const
          ).map(([id, key]) => (
            <button
              type="button"
              key={id}
              aria-pressed={tab === id}
              onClick={() => {
                setTab(id);
              }}
            >
              {t(key)}
            </button>
          ))}
        </div>
        <div hidden={tab !== "properties"}>
          <div ref={detailsRef} className="wb-details-slot" />
          <dl>
            <dt>{t("wbSample")}</dt>
            <dd>{task.sample.name}</dd>
            <dt>{t("wbTemplate")}</dt>
            <dd>{project.template?.name ?? "—"}</dd>
            <dt>
              {t("wbTemplateVersion", {
                version: project.template?.revision ?? 1,
              })}
            </dt>
            <dd>
              {project.label_set.name} · {project.label_set.version}
            </dd>
          </dl>
        </div>
        {tab === "history" && (
          <section>
            <h2>{t("wbHistory")}</h2>
            {task.revisions.length ? (
              <ol>
                {[...task.revisions].reverse().map((revision) => (
                  <li key={revision.id}>
                    <strong>{revision.actor}</strong>
                    <time dateTime={revision.created_at}>
                      {new Date(revision.created_at).toLocaleString(locale)}
                    </time>
                    <code>{revision.id}</code>
                    <pre>{JSON.stringify(revision.annotation, null, 2)}</pre>
                  </li>
                ))}
              </ol>
            ) : (
              <p>{t("wbNoHistory")}</p>
            )}
          </section>
        )}
        {tab === "reviews" && (
          <section>
            <h2>{t("wbReviews")}</h2>
            {task.reviews.length ? (
              <ol>
                {task.reviews.map((review) => (
                  <li key={review.id}>
                    <strong>
                      {review.actor} ·{" "}
                      {t(
                        review.decision === "approve"
                          ? "wbApproved"
                          : "wbRework",
                      )}
                    </strong>
                    <p>{review.issues.join("\n")}</p>
                    <time dateTime={review.created_at}>
                      {new Date(review.created_at).toLocaleString(locale)}
                    </time>
                  </li>
                ))}
              </ol>
            ) : (
              <p>{t("wbNoReviews")}</p>
            )}
          </section>
        )}
        {tab === "guide" && (
          <section>
            <h2>{t("wbGuidelines")}</h2>
            <p className="wb-guide">
              {[
                project.project.guidelines,
                typeof project.template?.component_config?.guidelines ===
                "string"
                  ? project.template.component_config.guidelines
                  : "",
              ]
                .filter(Boolean)
                .join("\n\n") || t("wbNoGuidelines")}
            </p>
          </section>
        )}
      </div>
    </aside>
  );
}
