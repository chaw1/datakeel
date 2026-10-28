# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Answer training distribution and leakage questions without changing datasets."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.training_parameters import (
    TrainingDistributionParams,
    TrainingLeakageParams,
)
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_versions
from datakeel.storage.training_store import (
    check_leakage,
    get_split,
    preview_leakage,
    preview_split,
)

TRAINING_TOOL_DESCRIPTIONS = {
    "training_distribution": (
        "Read per-class train/val/test counts, or preview a seeded 8:1:1 primary-label split. "
        "训练集按主标签切分、各类分布、按8:1:1切完各类分布怎样; only reads, never saves."
    ),
    "training_leakage": (
        "Check exact, image near-duplicate and group leakage with sample pairs and distances. "
        "有没有泄漏、跨集合重复; text similarity is unavailable; defaults to external directories."
    ),
}


def invoke_training(
    db: Database, name: str, arguments: JsonDocument, access: AccessContext
) -> FunctionResult:
    """Read version-bound facts and return the same measurements as the CLI and UI."""
    model = TrainingLeakageParams if name == "training_leakage" else TrainingDistributionParams
    params = model.model_validate(arguments.root)
    version_id = params.version_id
    if params.split_set_id is not None:
        split = get_split(db, params.dataset_id, params.split_set_id, access=access)
        if version_id is not None and split.version_id != version_id:
            message = "Split set does not belong to the requested version"
            raise ValidationError(message)
        version_id = split.version_id
        value = (
            check_leakage(db, params.dataset_id, split.id, access=access)
            if name == "training_leakage"
            else split
        )
    else:
        version_id = version_id or _latest_version(db, params.dataset_id, access)
        reader = preview_leakage if name == "training_leakage" else preview_split
        value = reader(db, params.dataset_id, version_id, params.request, access=access)
    return FunctionResult(
        function=name,
        asset_refs=[AssetRef(asset_id=params.dataset_id, version=version_id)],
        data=value.model_dump(mode="json"),
    )


def _latest_version(db: Database, dataset_id: str, access: AccessContext) -> str:
    versions = list_versions(db, dataset_id, access=access)
    if not versions:
        message = "Dataset has no immutable version"
        raise NotFoundError(message)
    return versions[-1].id
