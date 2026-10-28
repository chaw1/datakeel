# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Datasheet mutations must fail assertions at the actual sentence publication boundary."""

from datetime import UTC, datetime

from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact, DatasheetSection, DatasheetSentence
from datakeel.datasheets.validation import validate_sections


def _rejected(
    text: str, ids: tuple[str, ...], value: JsonValue = 12, field: str = "manifest.file_count"
) -> bool:
    fact = DatasheetFact(
        id="f1",
        chapter="composition",
        source_type="manifest",
        source_id="v1",
        field=field,
        value=value,
        recorded_at=datetime(2026, 10, 27, tzinfo=UTC),
    )
    result = validate_sections(
        (
            DatasheetSection(
                key="composition",
                title="Composition",
                sentences=(DatasheetSentence(text=text, fact_ids=ids),),
            ),
        ),
        (fact,),
        "en",
    )
    return not result.sections[1].sentences and bool(result.dropped_sentences)


def test_datasheet_invented_number_cannot_be_published() -> None:
    """Removing numeric support checks exposes a fabricated cardinality."""
    assert _rejected("The dataset contains 13 files.", ("f1",))


def test_datasheet_unseen_proper_name_cannot_be_published() -> None:
    """Removing content support checks exposes a previously unknown owner."""
    assert _rejected("Northstar is the owner.", ("f1",))


def test_datasheet_unknown_fact_cannot_be_published() -> None:
    """Unknown citations are forbidden independently of lexical or numeric checks."""
    assert _rejected("The dataset contains files.", ("missing",))


def test_datasheet_uncited_sentence_cannot_be_published() -> None:
    """Even plain grammar cannot become an asserted sentence without a citation."""
    assert _rejected("The dataset contains files.", ())


def test_datasheet_invented_date_cannot_be_published() -> None:
    """Removing normalized date checks exposes an unsupported collection date."""
    assert _rejected("Collection date: 2027-01-02.", ("f1",))


def test_datasheet_numeric_owner_name_cannot_be_published() -> None:
    """A count of one cannot establish an owner named with the written numeral."""
    assert _rejected("Owner='ONE'.", ("f1",), 1)


def test_datasheet_percentage_of_a_count_cannot_be_published() -> None:
    """A percentage restates only a ratio; a count of 50 files is not 50%."""
    assert _rejected("50% of the files are images.", ("f1",), 50)


def test_datasheet_byte_total_cannot_be_published_as_a_file_count() -> None:
    """A number written with a unit needs a cited fact measured in that unit."""
    assert _rejected(
        "The dataset contains 4,815,739 files.", ("f1",), 4815739, "manifest.total_bytes"
    )
