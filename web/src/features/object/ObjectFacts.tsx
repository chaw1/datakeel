import { useEffect, useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { objectFacts } from "./descriptors";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";

export function ObjectFacts({
  data,
  target,
}: {
  data: ObjectData;
  target: ObjectTarget;
}) {
  const { t } = useI18n();
  const [manifestHash, setManifestHash] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!data.version) return;
    let active = true;
    const encoded = new TextEncoder().encode(
      JSON.stringify(data.version.manifest),
    );
    void crypto.subtle.digest("SHA-256", encoded).then((value) => {
      if (active)
        setManifestHash(
          Array.from(new Uint8Array(value), (byte) =>
            byte.toString(16).padStart(2, "0"),
          ).join(""),
        );
    });
    return () => {
      active = false;
    };
  }, [data.version]);
  const digest = data.plan?.plan_digest ?? manifestHash;
  async function copy() {
    try {
      await navigator.clipboard.writeText(digest);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <section className="object-facts" aria-label={t("objFacts")}>
      {objectFacts(data, target).map((fact) => (
        <a
          className="object-fact"
          key={fact.label}
          href={fact.href}
          data-fact={fact.label}
        >
          <span>{t(fact.label)}</span>
          <strong>
            {fact.label === "objReceipt" && data.action
              ? t(data.action.status)
              : fact.value}
          </strong>
        </a>
      ))}
      {digest && (
        <button
          className="object-fact object-digest"
          onClick={() => {
            void copy();
          }}
          title={digest}
          aria-label={t(data.plan ? "objCopyDigest" : "objCopyManifest")}
        >
          <span>{t(data.plan ? "objDigest" : "objManifest")}</span>
          <code>{copied ? t("objCopied") : digest.slice(0, 12)}</code>
        </button>
      )}
    </section>
  );
}
