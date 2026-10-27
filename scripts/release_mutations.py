# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Release, recipient verification and upload mutations with measured regression targets."""

from scripts.mutation_models import Mutation

RELEASE_MUTATIONS = (
    Mutation(
        name="version-content-category",
        path="storage/version_diff.py",
        before="if before.sha256 != after.sha256:",
        after="if False:",
        case=(
            "tests/storage/test_version_diff.py::"
            "test_diff_five_categories_and_annotation_quality_evidence_changes"
        ),
        runner="pytest",
    ),
    Mutation(
        name="release-mandatory-approval",
        path="actions/registry.py",
        before='"publish_release": ("datasets:publish", False,',
        after='"publish_release": ("datasets:publish", True,',
        case="tests/storage/test_releases.py::test_publication_without_approval_is_denied",
        runner="pytest",
    ),
    Mutation(
        name="delivery-content-hash",
        path="delivery/checks.py",
        before="if actual != item.sha256:",
        after="if False:",
        case="tests/delivery/test_reconcile.py::test_fault_is_reported_in_its_category[byte-hashes]",
        runner="pytest",
    ),
    Mutation(
        name="delivery-manifest-hash",
        path="delivery/checks.py",
        before="if actual_manifest_hash != manifest.manifest_sha256:",
        after="if False:",
        case=(
            "tests/delivery/test_reconcile.py::"
            "test_manifest_checksum_detects_expected_metadata_tampering"
        ),
        runner="pytest",
    ),
    Mutation(
        name="delivery-metadata-types",
        path="delivery/checks.py",
        before=(
            "json.dumps(expected.get(key), sort_keys=True, ensure_ascii=False)\n"
            "        != json.dumps(actual.get(key), sort_keys=True, ensure_ascii=False)"
        ),
        after="expected.get(key) != actual.get(key)",
        case="tests/delivery/test_reconcile.py::test_metadata_type_corruption_is_detected",
        runner="pytest",
    ),
    Mutation(
        name="upload-final-chunk-size",
        path="storage/upload_service.py",
        before="if len(content) != expected_bytes(body, ordinal):",
        after="if False:",
        case="tests/api/test_uploads.py::test_http_chunk_upload_resume_and_download",
        runner="pytest",
    ),
    Mutation(
        name="upload-source-hash",
        path="storage/upload_files.py",
        before="target.stat().st_size != body.total_bytes or digest(target) != body.sha256",
        after="target.stat().st_size != body.total_bytes",
        case="tests/storage/test_uploads.py::test_missing_chunk_and_hash_failure_never_publish",
        runner="pytest",
    ),
    Mutation(
        name="portable-metadata-slash-labels",
        path="core/portable_metadata.py",
        before="return isinstance(value, str) and _private_uri(value.strip())",
        after=(
            "return isinstance(value, str) and "
            '(value.strip().startswith("/") or _private_uri(value.strip()))'
        ),
        case=(
            "tests/delivery/test_portable_metadata.py::"
            "test_slash_prefixed_labels_survive_with_their_counts"
        ),
        runner="pytest",
    ),
)
