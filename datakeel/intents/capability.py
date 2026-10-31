# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""An object that cannot do what the step asks: said as "cannot", never as a question.

A pre-label run only runs offline models that draw boxes. With a model that does another
annotation type the step would fail after confirmation, so the person hears that it cannot
be done and why, with the models that can run named as an alternative. The plan is not
rewritten into "use X instead?": choosing another model is the person's next sentence.
"""

from pydantic import JsonValue

from datakeel.core.intent_models import ChainStep
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.intents.plain_words import enum_label
from datakeel.storage.database import Database
from datakeel.storage.production_objects import production_objects


def _runs_prelabel(properties: dict[str, JsonValue]) -> bool:
    """What the pre-label run accepts today: an offline model that draws boxes."""
    capabilities = properties.get("capabilities")
    return (
        properties.get("provider") == "fake"
        and isinstance(capabilities, list)
        and "box" in capabilities
    )


def model_mismatch(db: Database, step: ChainStep, language: str) -> str | None:
    """Why a pre-label run cannot use this model, with the usable ones; None when it can."""
    wanted = step.params.get("model_id")
    if step.action != "run_prelabel" or not isinstance(wanted, str):
        return None
    query = ProductionObjectQuery(kind="model")
    models = {item.asset_ref.asset_id: item.properties for item in production_objects(db, query)}
    chosen = models.get(wanted)
    if chosen is None or _runs_prelabel(chosen):
        return None
    raw = chosen.get("capabilities")
    kinds = [enum_label(str(kind), language) for kind in raw] if isinstance(raw, list) else []
    name = str(chosen.get("name") or wanted)
    usable = [str(item.get("name") or key) for key, item in models.items() if _runs_prelabel(item)]
    if language == "zh":
        does = f"做的是{'、'.join(kinds)}标注" if kinds else "不是框标注模型"
        other = f"能跑的有 {'、'.join(usable)}" if usable else "要先登记一个框标注模型"
        return f"「{name}」{does}, 预标注现在只能用框标注模型, 所以做不了 ({other})"
    does = f"does {', '.join(kinds)}" if kinds else "is not a box model"
    other = f"models that can run: {', '.join(usable)}" if usable else "register a box model"
    return f'"{name}" {does} and pre-labelling only runs box models, so it cannot be done ({other})'
