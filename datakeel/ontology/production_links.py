# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declare production containment, membership and exact-revision relationships."""

from datakeel.ontology.models import LinkType

CONTAINMENT_DOMAINS = [
    "dataset",
    "version",
    "source",
    "table",
    "project",
    "task_package",
    "production_task",
]
CONTAINMENT_RANGES = [
    "version",
    "file",
    "artifact",
    "table",
    "column",
    "task_package",
    "production_task",
    "assignment",
    "annotation_revision",
    "review",
]


def production_links() -> list[LinkType]:
    """Use the shared ontology link contract for the identities stored on production facts."""
    definitions = (
        ("member_of", ["user"], ["team"], "User team membership"),
        ("holds_role", ["user"], ["role"], "Approved global or project role binding"),
        ("has_skill", ["user"], ["skill"], "Recorded annotation capability"),
        ("assigned_to", ["assignment"], ["user"], "Exclusive effective task-stage ownership"),
        ("review_of", ["review"], ["annotation_revision"], "Decision about an exact revision"),
        (
            "previous_revision",
            ["annotation_revision"],
            ["annotation_revision"],
            "Append-only previous revision pointer",
        ),
        (
            "uses",
            ["project"],
            ["version", "label_set", "template", "model"],
            "Pinned input version and production configuration",
        ),
    )
    return [
        LinkType(
            id=kind,
            domain=domain,
            range=target,
            cardinality="many-to-many",
            semantics=kind,
            description=description,
        )
        for kind, domain, target, description in definitions
    ]
