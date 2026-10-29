# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declare the people and production ontology families using their boundary models."""

from pydantic import BaseModel

from datakeel.core.identity_models import Role, Skill, Team, User
from datakeel.core.production_catalog_models import (
    LabelSet,
    PrelabelRun,
    ProductionModel,
    ProductionTemplate,
)
from datakeel.core.production_models import (
    AnnotationRevision,
    Assignment,
    ProductionTask,
    Project,
    Review,
    TaskPackage,
)

PRODUCTION_KINDS: dict[str, type[BaseModel]] = {
    "user": User,
    "team": Team,
    "role": Role,
    "skill": Skill,
    "label_set": LabelSet,
    "template": ProductionTemplate,
    "project": Project,
    "task_package": TaskPackage,
    "production_task": ProductionTask,
    "assignment": Assignment,
    "annotation_revision": AnnotationRevision,
    "review": Review,
    "model": ProductionModel,
    "prelabel_run": PrelabelRun,
}
