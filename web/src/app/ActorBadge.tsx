import { Icon } from "../components/Icon";
import { useI18n } from "../i18n/useI18n";

import { defaultActorIdentity } from "./useActorIdentity";

import type { ActorIdentity } from "./useActorIdentity";

export function ActorBadge({ identity }: { identity?: ActorIdentity }) {
  const { t } = useI18n();
  const resolved = identity ?? defaultActorIdentity;
  const roleLabel = resolved.zeroUsers
    ? t("actorLocalMode")
    : resolved.scopes.includes("*") ||
        resolved.scopes.includes("manage_users") ||
        resolved.scopes.includes("define_role")
      ? t("actorRoleAdmin")
      : resolved.scopes.length > 0
        ? t("actorRoleScoped", { count: resolved.scopes.length })
        : t("actorRoleReadOnly");
  const summary = t("actorBadgeSummary", {
    actor: resolved.actor,
    role: roleLabel,
  });
  return (
    <span
      className="actor-badge"
      data-actor={resolved.actor}
      data-zero-users={resolved.zeroUsers ? "true" : "false"}
      aria-label={summary}
      title={summary}
    >
      <Icon name="user" size={13} />
      <code className="actor-id">{resolved.actor}</code>
      <span className="actor-sep" aria-hidden="true">
        {"·"}
      </span>
      <span className="actor-role">{roleLabel}</span>
    </span>
  );
}
