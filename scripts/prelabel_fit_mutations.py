# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Anchors where AI prelabel meets upright images, locked templates and rework handovers.

The model sees the upright pixels its display-frame drafts are recorded in; accuracy and
pre-review read legacy stored-frame drafts upright; both read the project's locked template
version; and whoever triggered a pass-through stays out of review after a rework handover.
"""

from scripts.mutation_models import Mutation

_FIT = "tests/storage/test_prelabel_upright_and_locked.py::"

PRELABEL_FIT_MUTATIONS = (
    Mutation(
        name="prelabel-model-sees-upright-pixels",
        path="storage/workbench_pixels.py",
        before="        return ImageOps.exif_transpose(source)\n",
        after="        source.load()\n        return source.copy()\n",
        case=_FIT + "test_cloud_drafts_frame_the_upright_object_as_display_rows[6]",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-references-read-upright",
        path="storage/production_prelabel_refs.py",
        before="        row.id: revision_view(session, row)\n",
        after="        row.id: AnnotationRevision.model_validate(row.payload)\n",
        case=_FIT + "test_accuracy_and_pre_review_read_a_legacy_draft_upright",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-drafts-read-upright",
        path="storage/production_ai_facts.py",
        before="        revision = revision_view(session, row)\n",
        after="        revision = AnnotationRevision.model_validate(row.payload)\n",
        case=_FIT + "test_accuracy_and_pre_review_read_a_legacy_draft_upright",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-kinds-use-locked-template",
        path="storage/production_cloud_prelabel.py",
        before="    template = locked_template(session, project)\n",
        after=(
            "    template = locked_template("
            'session, project.model_copy(update={"template_version": None}))\n'
        ),
        case=_FIT + "test_cloud_kinds_and_pre_review_rules_follow_the_locked_template",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-uses-locked-template",
        path="storage/production_ai_facts.py",
        before="        return locked_template(session, project)\n",
        after=(
            "        return locked_template("
            'session, project.model_copy(update={"template_version": None}))\n'
        ),
        case=_FIT + "test_cloud_kinds_and_pre_review_rules_follow_the_locked_template",
        runner="pytest",
    ),
    Mutation(
        name="separation-counts-pass-through-trigger",
        path="storage/production_separation.py",
        before='    ProductionRevisionRow.payload["pass_through"].as_string().is_not(None),\n',
        after="    ProductionRevisionRow.id.is_(None),\n",
        case=_FIT + "test_pass_through_trigger_stays_out_of_review_after_a_rework_handover",
        runner="pytest",
    ),
)
