# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify the shared detector protects operators, profiles and persisted memory."""

from pathlib import Path

import pytest

from datakeel.core.memory_models import MemoryCreate
from datakeel.core.pii import PiiType
from datakeel.memory.service import create_memory, get_memory
from datakeel.operators import REGISTRY
from datakeel.operators.table.io import TableData
from datakeel.operators.table.params import ProfileParams
from datakeel.operators.table.profile import profile_data
from datakeel.storage.database import Database
from tests.core.pii_samples import card, identity
from tests.operators.factories import FileFactory


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("person@example.org", "email"),
        ("+1 (415) 555-0132", "phone"),
        (identity(), "china_id"),
        (card(), "bank_card"),
        (f"{203}.0.113.29", "ip"),
        ("sk-" + "a1B2c3D4" * 4, "secret"),
        ("https://" + "user:pass@" + "example.org/data", "credential_url"),
    ],
)
def test_shared_privacy_when_new_shape_present_protects_every_existing_consumer(
    value: str, kind: PiiType, db: Database, make_file: FileFactory, output_dir: Path
) -> None:
    """Every existing write/profile path consumes the same validated privacy findings."""
    result = REGISTRY["text.pii_redact"].run([make_file(value)], output_dir)
    assert Path(result.files[0].path).read_text() == f"[{kind.upper()}]"
    assert result.quality["redactions"] == 1
    memory = create_memory(db, MemoryCreate(content=f"Remember {value}"))
    assert get_memory(db, memory.id).content == f"Remember [{kind.upper()}]"
    profile = profile_data(
        TableData(columns=("contact",), rows=((value,),), row_numbers=(2,)), ProfileParams()
    )
    assert profile.columns[0].pii_kinds == (kind,)
    assert value not in profile.model_dump_json()
    assert profile.columns[0].distribution.numeric is None


def test_operator_when_contact_toggles_disabled_keeps_other_privacy_classes_active(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Legacy contact toggles and custom labels remain useful after shared detection expands."""
    text = "person@example.org, +1 (415) 555-0132; " + card()
    result = REGISTRY["text.pii_redact"].run(
        [make_file(text)], output_dir, {"emails": False, "phones": False, "replacement": "hidden"}
    )
    assert Path(result.files[0].path).read_text() == "person@example.org, +1 (415) 555-0132; hidden"
    assert result.quality["redactions"] == 1
