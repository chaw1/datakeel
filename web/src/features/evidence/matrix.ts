import { objectHref } from "../object/navigation";

import { assertionConcept, assertionValue } from "./assertions";

import type { Assertion, EvidenceSample } from "../../api/types";
import type { AnchorRange } from "../../components/Anchor";
import type { FootnoteItem } from "../../components/Footnotes";

export const matrixPredicates = [
  "mentions",
  "annotated_as",
  "label_gap",
] as const;
export function reviewOrder(assertions: Assertion[]): Assertion[] {
  return [...assertions].sort(
    (a, b) =>
      Number(assertionValue(b) === "unknown") -
        Number(assertionValue(a) === "unknown") ||
      Number(b.status === "candidate") - Number(a.status === "candidate"),
  );
}
export function concepts(sample: EvidenceSample): string[] {
  const names = [
    ...new Set(
      reviewOrder(sample.assertions)
        .filter((item) =>
          matrixPredicates.some((predicate) => item.predicate === predicate),
        )
        .map(assertionConcept)
        .filter((value): value is string => Boolean(value)),
    ),
  ];
  const position = (name: string) =>
    Math.min(
      ...sample.assertions
        .filter((item) => assertionConcept(item) === name)
        .flatMap((item) =>
          item.anchors.flatMap((anchor) =>
            anchor.selector && "start" in anchor.selector
              ? [anchor.selector.start]
              : [],
          ),
        ),
      Infinity,
    );
  return names.sort((a, b) => position(a) - position(b));
}
export function anchors(sample: EvidenceSample): AnchorRange[] {
  const names = concepts(sample);
  return sample.assertions.flatMap((assertion) =>
    assertion.anchors.flatMap((anchor) => {
      const selector = anchor.selector;
      const concept = assertionConcept(assertion);
      return selector && "start" in selector && concept
        ? [
            {
              start: selector.start,
              end: selector.end,
              id: concept,
              number: names.indexOf(concept) + 1,
            },
          ]
        : [];
    }),
  );
}
export function sourceId(sample: EvidenceSample, assertion: Assertion): string {
  return `${assertion.extractor.id}:${assertion.extractor.version}:${sample.source_version}`;
}
export function evidenceSources(samples: EvidenceSample[]): FootnoteItem[] {
  const items = new Map<string, FootnoteItem>();
  const mixed =
    new Set(samples.map((sample) => sample.source_version)).size > 1;
  const ordered = samples
    .flatMap((sample) =>
      sample.assertions.map((assertion) => ({ sample, assertion })),
    )
    .sort((a, b) => {
      const rank = (assertion: Assertion) => {
        const index = matrixPredicates.findIndex(
          (predicate) => predicate === assertion.predicate,
        );
        return index < 0 ? matrixPredicates.length : index;
      };
      return rank(a.assertion) - rank(b.assertion);
    });
  for (const { sample, assertion } of ordered) {
    const id = sourceId(sample, assertion);
    if (!items.has(id))
      items.set(id, {
        id,
        label: `${assertion.extractor.id} · ${assertion.extractor.version}${mixed ? ` · ${sample.source_version}` : ""}`,
        href: objectHref({
          kind: "version",
          id: sample.source_version,
          datasetId: sample.dataset_id,
          tab: "facts",
        }),
      });
  }
  return [...items.values()];
}
