# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assertion-only anchors for E4 cursor snapshots, authorization and typed failure reads."""

from scripts.mutation_models import Mutation

VECTOR_QUERY_MUTATIONS = (
    Mutation(
        name="vector-query-registered-identity",
        path="api/identity_access.py",
        before='        ("POST", "/api/evidence/vector/query"),\n',
        after="",
        case="tests/api/test_identity_access.py::test_registered_actor_can_use_vector_read_post",
        runner="pytest",
    ),
    Mutation(
        name="vector-query-cursor-signature",
        path="storage/vector_cursor.py",
        before=(
            "if not hmac.compare_digest(signature, "
            "hmac.digest(_SIGNING_KEY, payload, hashlib.sha256)):"
        ),
        after="if False:",
        case="tests/api/test_vector_query.py::test_vector_cursor_snapshot_forgery_filters_actor_and_expiry",
        runner="pytest",
    ),
    Mutation(
        name="vector-query-cursor-expiry",
        path="storage/vector_cursor.py",
        before="or cursor.expires <= int(utcnow().timestamp())",
        after="or False",
        case="tests/api/test_vector_query.py::test_vector_cursor_expiry_and_page_bounds",
        runner="pytest",
    ),
    Mutation(
        name="vector-query-cursor-review",
        path="storage/vector_queries.py",
        before='return vector_hash(self.model_dump(mode="json"))',
        after='return vector_hash(self.model_dump(mode="json", exclude={"facts"}))',
        case="tests/api/test_vector_query.py::test_vector_review_append_only_and_rerun_require_fresh_pagination",
        runner="pytest",
    ),
    Mutation(
        name="vector-query-all-r-authorization",
        path="storage/vector_queries.py",
        before=(
            "require_access_in_session(session, tuple(dict.fromkeys(refs)), access, record=False)"
        ),
        after="require_access_in_session(session, (), access, record=False)",
        case="tests/api/test_vector_query_access.py::test_vector_query_all_r_authorization_revocation_and_no_side_effects",
        runner="pytest",
    ),
    Mutation(
        name="vector-query-empty-r-stale",
        path="storage/vector_query_snapshot.py",
        before="states.append(scope is not None and current[0].members == scope.references)",
        after="states.append(True)",
        case="tests/api/test_vector_query_access.py::test_vector_query_zero_candidates_still_validates_full_reference_scope",
        runner="pytest",
    ),
    Mutation(
        name="vector-query-partial-status",
        path="storage/vector_query_snapshot.py",
        before='if any(n.status == "partial_success" for n in nodes)',
        after="if False",
        case="tests/api/test_vector_query.py::test_vector_partial_failure_is_not_empty_success",
        runner="pytest",
    ),
    Mutation(
        name="vector-query-zero-rerun",
        path="storage/vector_query_snapshot.py",
        before="producer == event.event_id",
        after="True",
        case="tests/api/test_vector_query_status.py::test_vector_query_old_zero_result_is_stale_after_rerun",
        runner="pytest",
    ),
)
