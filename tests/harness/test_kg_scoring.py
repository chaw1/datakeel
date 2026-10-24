# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent scorer regressions preserve published counts and adversarial edge cases."""

from datakeel.core.kg_eval_models import (
    GoldEntity,
    GoldRelation,
    KGCase,
    ScoredEntity,
    ScoredRecord,
    ScoredRelation,
)
from datakeel.kg.loader import contracts_path, get_schema
from datakeel.kg_eval.alignment import evidence_located, match_entity, norm, verified
from datakeel.kg_eval.loader import load_cases, load_recording, original_records
from datakeel.kg_eval.scoring import gate, prf, score_passages, score_views


def _case() -> KGCase:
    return KGCase(
        id="test",
        lang="en",
        text="Alice maintains Atlas. Atlas uses Redis.",
        entities=(
            GoldEntity(name="Alice", type="person", aliases=("Dr. Alice",)),
            GoldEntity(name="Atlas", type="system"),
            GoldEntity(name="Redis", type="system"),
        ),
        relations=(GoldRelation(head="Alice", relation="owns", tail="Atlas"),),
        optional=(GoldRelation(head="Atlas", relation="uses", tail="Redis"),),
        traps=(GoldRelation(head="Alice", relation="uses", tail="Redis"),),
    )


def test_recorded_qwen_exact_metrics_and_verified_subset() -> None:
    """Keep the original false positives, omissions and failed evidence in the raw path."""
    schema = get_schema()
    suite, _ = load_cases(schema)
    records = original_records(load_recording(contracts_path() / "recordings/qwen3.5.yaml"), suite)
    result = score_views(records, suite, {relation.name for relation in schema.relations})
    assert result.all.relation_strict == prf(99, 16, 15)
    assert result.all.relation_pair == prf(102, 9, 12)
    assert result.all.entity_typed == result.all.entity_untyped == prf(157, 1, 4)
    assert result.all.trap_hits == 3
    assert result.all.endpoint_unmapped == 2
    assert result.all.pred_relations == 118
    assert result.all.evidence_located == 0.966
    assert result.all.verified_ratio == 0.958
    assert result.zh.relation_strict == prf(55, 7, 8)
    assert result.en.relation_strict == prf(44, 9, 7)
    assert result.verified.relation_strict == prf(96, 14, 18)
    assert result.all.input_tokens is None
    assert result.all.cost_usd is None


def test_recorded_flash_exact_metrics_and_usage() -> None:
    """Keep the optional-relation exemption and recorded usage independent of product filters."""
    schema = get_schema()
    suite, _ = load_cases(schema)
    records = original_records(
        load_recording(contracts_path() / "recordings/deepseek-flash.yaml"), suite
    )
    result = score_views(records, suite, {relation.name for relation in schema.relations})
    assert result.all.relation_strict == result.all.relation_pair == prf(114, 1, 0)
    assert result.all.entity_typed == result.all.entity_untyped == prf(153, 0, 8)
    assert result.all.trap_hits == result.all.endpoint_unmapped == 0
    assert result.verified.relation_strict == result.all.relation_strict
    assert result.all.input_tokens == 39321
    assert result.all.output_tokens == 8025
    assert result.zh.relation_strict == prf(63, 0, 0)
    assert result.en.relation_strict == prf(51, 1, 0)


def test_normalization_and_alias_alignment_preserve_reference_rules() -> None:
    """Distinguish scorer prefix deletion and containment ranking from product identity."""
    assert norm("  The \uff21\uff4c\uff49\uff43\uff45  ;") == "alice"
    assert norm("Dr. Alice") == norm("its Alice") == norm("their Alice") == "alice"
    case = _case().model_copy(
        update={
            "entities": (
                GoldEntity(name="Analytics", type="system"),
                GoldEntity(name="Analytics team", type="organization"),
                GoldEntity(name="X", type="person"),
            )
        }
    )
    assert match_entity("analytics", case, "organization") == "Analytics"
    assert match_entity("Analytics team unit", case) == "Analytics team"
    assert match_entity("Analytics team unit has many extra characters", case) is None
    assert match_entity("Xx", case) is None
    assert match_entity(" ", case) is None
    tied = case.model_copy(
        update={
            "entities": (
                GoldEntity(name="a word", type="person"),
                GoldEntity(name="word z", type="system"),
            )
        }
    )
    assert match_entity("word", tied, "person") == "a word"
    assert match_entity("word", tied, "system") == "word z"


def test_optional_unmapped_duplicate_outside_schema_and_trap_counts() -> None:
    """Exercise the reference denominators without filtering malformed model claims."""
    correct = ScoredRelation(head="Alice", relation="owns", tail="Atlas")
    record = ScoredRecord(
        pid="test",
        entities=(ScoredEntity(name="Alice", type="system"), ScoredEntity(name="Phantom")),
        relations=(
            correct,
            correct,
            ScoredRelation(head="Atlas", relation="uses", tail="Redis"),
            ScoredRelation(head="Alice", relation="uses", tail="Redis"),
            ScoredRelation(head="Phantom", relation="owns", tail="Atlas"),
            ScoredRelation(head="Atlas", relation="unknown label", tail="Alice"),
            ScoredRelation(head="Alice", relation="owns", tail="Alice"),
        ),
    )
    result = score_passages((record,), (_case(),), {"owns", "uses"})
    assert result.relation_strict == prf(1, 4, 0)
    assert result.relation_pair == prf(1, 3, 0)
    assert result.entity_typed == prf(0, 2, 3)
    assert result.entity_untyped == prf(1, 1, 2)
    assert result.trap_hits == 1
    assert result.endpoint_unmapped == 2
    assert result.label_outside_schema == 0.143


def test_grounding_recording_and_product_flags_remain_independent() -> None:
    """Recorded gating requires both names and evidence; product uses its own stored verdict."""
    text = _case().text
    relation = ScoredRelation(head="Alice", relation="owns", tail="Atlas")
    assert verified(text, relation)
    assert not evidence_located(text, relation)
    located_relation = relation.model_copy(update={"head_span": (0, 5), "tail_span": (16, 21)})
    assert evidence_located(text, located_relation)
    wrong = relation.model_copy(
        update={"evidence": "Alice owns Atlas", "ev_start": 0, "ev_end": 21}
    )
    assert not verified(text, wrong)
    assert not evidence_located(text, wrong)
    hallucination = relation.model_copy(update={"head": "Vivo"})
    assert not verified(text, hallucination)
    assert not verified(text, relation.model_copy(update={"verification": "needs_review"}))
    assert verified(text, wrong.model_copy(update={"verification": "verified"}))
    assert not verified(text, relation.model_copy(update={"evidence": "Alice"}))


def test_missing_error_untyped_fallback_and_empty_scores() -> None:
    """Preserve zero denominators and the reference missing-passage convention."""
    relation = ScoredRelation(head="Alice", relation="owns", tail="Atlas")
    record = ScoredRecord(pid="test", relations=(relation,), error="parse_error")
    ignored = ScoredRecord(pid="outside", error="ignored")
    result = score_passages((record, ignored), (_case(),), {"owns"})
    assert result.entity_typed == prf(0, 2, 3)
    assert result.entity_untyped == prf(2, 0, 1)
    assert result.errors == result.failed_blocks == 1
    assert score_passages((), (_case(),), {"owns"}).relation_strict == prf(0, 0, 1)
    assert score_passages((), (), set()).relation_strict == prf(0, 0, 0)
    assert gate((record, ignored), (_case(),)) == (record,)
