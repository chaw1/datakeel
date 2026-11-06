# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assertion-only anchors for publication lock ordering and real Session lifecycles."""

from scripts.mutation_models import Mutation

_TRANSACTION_LOCK = """    if session.get_bind().dialect.name != "postgresql":
        return
    transaction = session.get_nested_transaction() or session.get_transaction() or session.begin()
    held = cast("set[SessionTransaction]", session.info.get(_LOCK_TRANSACTIONS, set()))
    ancestor: SessionTransaction | None = transaction
    while ancestor is not None:
        if ancestor in held:
            return
        ancestor = ancestor.parent
    session.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtext(current_schema()), "
            "hashtext('evidence_projection'))"
        )
    )
    session.info.setdefault(_LOCK_TRANSACTIONS, set()).add(transaction)"""

_SESSION_LOCK = """    if session.get_bind().dialect.name != "postgresql":
        return
    if session.info.get("lock"):
        return
    session.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtext(current_schema()), "
            "hashtext('evidence_projection'))"
        )
    )
    session.info["lock"] = True"""

_EARLY_LOCK = """    if event.operator in VECTOR_OPERATORS:
        lock_evidence(session)
    prior = session.scalar("""

VECTOR_LOCK_MUTATIONS = (
    Mutation(
        name="vector-lock-before-predecessors",
        path="storage/evidence_store.py",
        before=_EARLY_LOCK,
        after="    prior = session.scalar(",
        case="tests/evidence/test_vector_publication_locks.py::test_first_vector_reads_follow_projection_lock",
        runner="pytest",
    ),
    Mutation(
        name="vector-lock-legal-interleaving",
        path="storage/evidence_store.py",
        before=_EARLY_LOCK,
        after="    prior = session.scalar(",
        case="tests/evidence/test_vector_publication_locks.py::test_same_key_publication_committed_before_lock_grant_is_not_rejected",
        runner="pytest",
    ),
    Mutation(
        name="vector-lock-transaction-dedup",
        path="storage/vector_cache.py",
        before="if ancestor in held:",
        after="if False:",
        case="tests/storage/test_evidence_locks.py::test_repeated_calls_in_one_transaction_execute_once",
        runner="pytest",
    ),
    *(
        Mutation(
            name=f"vector-lock-session-{end}",
            path="storage/vector_cache.py",
            before=_TRANSACTION_LOCK,
            after=_SESSION_LOCK,
            case=f"tests/storage/test_evidence_locks.py::test_new_transaction_on_same_session_reacquires_lock[{end}]",
            runner="pytest",
        )
        for end in ("commit", "rollback", "close")
    ),
    Mutation(
        name="vector-lock-savepoint-rollback",
        path="storage/vector_cache.py",
        before="    held.discard(transaction)",
        after=(
            "    if transaction in held and transaction.parent is not None:\n"
            "        held.add(transaction.parent)\n"
            "    held.discard(transaction)"
        ),
        case="tests/storage/test_evidence_locks.py::test_first_lock_inside_rolled_back_savepoint_is_reacquired",
        runner="pytest",
    ),
    Mutation(
        name="vector-lock-savepoint-release",
        path="storage/vector_cache.py",
        before="        held.add(nested.parent)",
        after="        held.add(nested)",
        case="tests/storage/test_evidence_locks.py::test_committed_savepoint_promotes_lock_until_root_ends",
        runner="pytest",
    ),
    Mutation(
        name="vector-lock-ordinary-publication",
        path="storage/evidence_store.py",
        before=_EARLY_LOCK,
        after="    lock_evidence(session)\n    prior = session.scalar(",
        case="tests/evidence/test_vector_publication_locks.py::test_ordinary_publication_never_calls_projection_lock",
        runner="pytest",
    ),
)
