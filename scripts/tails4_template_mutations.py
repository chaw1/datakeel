# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Template version locks, signed upgrade plans and the legacy lock migration (TAILS-4 R1)."""

from scripts.mutation_models import Mutation

_LOCK = "tests/storage/test_production_template_lock.py::"
_MIGRATION = "tests/storage/test_production_template_migration.py::"

TEMPLATE_LOCK_MUTATIONS = (
    Mutation(
        name="template-lock-validation-reads-locked-version",
        path="storage/production_catalog.py",
        before=(
            "    _validate_geometry(annotation)\n    template = locked_template(session, project)"
        ),
        after=(
            "    _validate_geometry(annotation)\n"
            "    template = require_template(session, project.template_id) "
            "if project.template_id else None"
        ),
        case=_LOCK + "test_template_and_label_changes_leave_both_sharing_projects_unchanged",
        runner="pytest",
    ),
    Mutation(
        name="template-lock-project-records-creation-revision",
        path="storage/production_projects.py",
        before="            template_version=template_version,",
        after="            template_version=None,",
        case=_LOCK + "test_template_and_label_changes_leave_both_sharing_projects_unchanged",
        runner="pytest",
    ),
    Mutation(
        name="template-lock-every-revision-recorded",
        path="storage/production_catalog_changes.py",
        before="    record_template_version(session, value)\n    return value",
        after="    return value",
        case=_LOCK + "test_every_saved_revision_stays_readable_for_an_explicit_upgrade",
        runner="pytest",
    ),
    Mutation(
        name="template-upgrade-moves-to-target-version",
        path="storage/production_template_upgrade.py",
        before='"template_version": plan.to_template_version,',
        after='"template_version": plan.from_template_version,',
        case=_LOCK + "test_signed_upgrade_changes_only_that_project_and_its_checks",
        runner="pytest",
    ),
    Mutation(
        name="template-upgrade-counts-failing-objects-once",
        path="storage/production_template_upgrade.py",
        before="invalid += bool(issues)",
        after="invalid += len(issues)",
        case=_LOCK + "test_upgrade_plan_counts_changes_and_non_compliant_annotations_exactly",
        runner="pytest",
    ),
    Mutation(
        name="template-upgrade-lists-removed-labels",
        path="storage/production_template_upgrade.py",
        before="removed=tuple(sorted(old.keys() - new.keys())),\n        renamed=",
        after="removed=(),\n        renamed=",
        case=_LOCK + "test_upgrade_plan_counts_changes_and_non_compliant_annotations_exactly",
        runner="pytest",
    ),
    Mutation(
        name="template-upgrade-newly-required-attributes",
        path="storage/production_template_upgrade.py",
        before="if item.required and (key not in old or not old[key].required)",
        after="if item.required and key in old",
        case=_LOCK + "test_upgrade_plan_counts_changes_and_non_compliant_annotations_exactly",
        runner="pytest",
    ),
    Mutation(
        name="template-upgrade-refuses-downgrades",
        path="storage/production_template_upgrade.py",
        before="if before is not None and after.revision < before.revision:",
        after="if False:",
        case=_LOCK + "test_upgrade_refuses_no_change_downgrade_and_archived_targets",
        runner="pytest",
    ),
    Mutation(
        name="template-lock-legacy-projects-locked",
        path="storage/production_template_versions.py",
        before='payload["template_version"] = current[template_id]',
        after='payload["template_version"] = None',
        case=_MIGRATION
        + "test_legacy_projects_lock_to_the_revision_they_used_and_rerun_changes_nothing",
        runner="pytest",
    ),
)
