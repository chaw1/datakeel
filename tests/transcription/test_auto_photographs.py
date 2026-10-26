# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep ordinary photographed and scanned text local despite irrelevant background pixels."""

from io import BytesIO
from typing import Literal

import numpy as np
import pytest
from PIL import Image

from datakeel.transcription.auto import decide_auto_route
from tests.transcription.auto_photo_fixtures import (
    card_photograph,
    dark_tabletop_card,
    edge_touching_unrecognized_figure,
    incomplete_scanned_page,
    low_contrast_paragraph,
    scanned_paragraph,
)


@pytest.mark.parametrize(
    ("paper", "noise", "seed"),
    [(155, 3, 11), (175, 5, 23), (190, 8, 37), (205, 12, 41), (220, 16, 53), (235, 19, 67)],
)
def test_grey_noisy_scan_with_dark_surround_stays_local(paper: int, noise: int, seed: int) -> None:
    """Paper tone and scanner grain do not encode a disabled row or missing text."""
    decision = decide_auto_route(*scanned_paragraph(paper, noise, seed))
    assert decision.route == "ocr"
    assert decision.reasons == ("clean_text",)


@pytest.mark.parametrize("kind", ["stripes", "wood"])
@pytest.mark.parametrize("variant", [0, 1, 2])
def test_perspective_card_on_textured_table_stays_local(
    kind: Literal["stripes", "wood"], variant: int
) -> None:
    """Exterior stripes and a smooth shadow cannot replace ordinary paragraph semantics."""
    decision = decide_auto_route(*card_photograph(kind, variant))
    assert decision.route == "ocr"
    assert decision.reasons == ("clean_text",)


@pytest.mark.parametrize(("paper", "contrast"), [(255, 65), (240, 60), (210, 50), (185, 45)])
def test_uniform_low_contrast_clear_paragraph_stays_local(paper: int, contrast: int) -> None:
    """Uniform faint print lacks the relative row contrast needed for cancellation."""
    decision = decide_auto_route(*low_contrast_paragraph(paper, contrast, 79))
    assert decision.route == "ocr"
    assert decision.reasons == ("clean_text",)


@pytest.mark.parametrize("kind", ["stripes", "wood"])
def test_short_card_on_large_background_is_not_sparse(kind: Literal["stripes", "wood"]) -> None:
    """A complete short card must be judged inside its document rather than its tabletop."""
    decision = decide_auto_route(*card_photograph(kind, 1, short=True))
    assert decision.route == "ocr"
    assert decision.reasons == ("clean_text",)


@pytest.mark.parametrize("variant", [0, 1, 2])
def test_perspective_card_annotations_enclose_rendered_glyphs(variant: int) -> None:
    """The projected OCR rectangles cover the transformed ink rather than invented positions."""
    image, result = card_photograph("wood", variant)
    with Image.open(BytesIO(image.png)) as source:
        glyphs = np.asarray(source.convert("L")) < 80
    covered = np.zeros(glyphs.shape, dtype=np.bool_)
    for line in result.lines:
        x1, y1, x2, y2 = line.bbox
        left, top = max(0, int(x1) - 1), max(0, int(y1) - 1)
        right, bottom = int(np.ceil(x2)) + 2, int(np.ceil(y2)) + 2
        assert np.count_nonzero(glyphs[top:bottom, left:right]) > 30
        covered[top:bottom, left:right] = True
    assert not np.any(glyphs & ~covered)


@pytest.mark.parametrize("kind", ["figure", "label"])
def test_partial_scanner_border_does_not_hide_incomplete_ocr(
    kind: Literal["figure", "label"],
) -> None:
    """Two visible scanner borders cannot crop away a missing figure or a sparse full page."""
    decision = decide_auto_route(*incomplete_scanned_page(kind))
    assert decision.route == "vlm"
    assert "sparse_text" in decision.reasons


def test_paper_edge_touching_figure_preserves_incomplete_ocr_signal() -> None:
    """A tiny bright glyph cavity cannot erase an unrecognized figure on the same paper."""
    decision = decide_auto_route(*edge_touching_unrecognized_figure())
    assert decision.route == "vlm"
    assert "sparse_text" in decision.reasons


@pytest.mark.parametrize("surface", [10, 20, 50, 90, 120])
def test_complete_card_on_dark_tabletop_stays_local(surface: int) -> None:
    """Exterior pixels darker than the text must not look like missing document content."""
    decision = decide_auto_route(*dark_tabletop_card(surface))
    assert decision.route == "ocr"
    assert decision.reasons == ("clean_text",)
