# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read only the explicitly selected upstream snapshots, with no transport or code loading."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from scripts.we_e1.models import EvidenceFile
from scripts.we_e1.preprocess import sha256

COMMONS_PAGEID = 152924098
COMMONS_REVID = 1199020912
COMMONS_RAW = "cc0-original/file-metadata.json"
COMMONS_JPG = "cc0-original/Bright_Lights_Ceiling.jpg"
COMMONS_CANDIDATES = "cc0-candidates/category.json"


class Upstream(BaseModel):
    """Parse required upstream fields; preserve unknown fields in the hash-bound raw file."""

    # Upstream responses evolve; only our own artifact boundaries forbid extra fields.
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class DatasetAPI(Upstream):
    """Identify the actual public repository revision, never a fabricated page revision."""

    id: Literal["google/wiki40b"]
    sha: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    private: Literal[False]
    gated: Literal[False]


class WikiRow(Upstream):
    """Keep the original Wiki-40B text and opaque version identifier verbatim."""

    wikidata_id: Annotated[str, Field(pattern=r"^Q[0-9]+$")]
    text: Annotated[str, Field(min_length=1)]
    version_id: Annotated[str, Field(min_length=1)]


class IndexedRow(Upstream):
    """Pin the server's selected row index."""

    row_idx: int
    row: WikiRow


class Rows(Upstream):
    """Accept only the four preselected development rows from a complete response."""

    rows: tuple[IndexedRow, ...]
    partial: Literal[False]


class Revision(Upstream):
    """Retain the Commons description-page revision separately from the image hash."""

    revid: int
    timestamp: str


class ImageInfo(Upstream):
    """Bind original image bytes and untouched extended metadata."""

    size: int
    width: int
    height: int
    url: str
    descriptionurl: str
    sha1: Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
    extmetadata: dict[str, JsonValue]


class CandidatePage(Upstream):
    """Represent one known Commons candidate, with no candidate enumeration."""

    pageid: int
    title: str
    imageinfo: tuple[ImageInfo, ...]


class Page(CandidatePage):
    """Bind the selected candidate to its description revision."""

    revisions: tuple[Revision, ...]


class Query(Upstream):
    """Decode the original Commons page mapping."""

    pages: dict[str, Page]


class CandidateQuery(Upstream):
    """Read candidate metadata without requiring description revisions."""

    pages: dict[str, CandidatePage]


class CandidateResponse(Upstream):
    """Retain only explicitly selected candidate data; never fetch continuation pages."""

    query: CandidateQuery


class CommonsResponse(Upstream):
    """Parse the saved API envelope as data only."""

    query: Query


def local_bytes(root: Path, name: str) -> bytes:
    """Reject traversal and symlinks before opening an explicitly named input."""
    relative = Path(name)
    candidate = root / relative
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        msg = "public input path must be relative"
        raise ValueError(msg)
    if not candidate.resolve().is_relative_to(root.resolve()) or any(
        path.is_symlink() for path in (candidate, *candidate.parents)
    ):
        msg = "public input escaped development root or used symlink"
        raise ValueError(msg)
    return candidate.read_bytes()


def evidence(root: Path, name: str) -> EvidenceFile:
    """Hash original bytes rather than a parsed or rewritten surrogate."""
    return EvidenceFile(path=name, sha256=sha256(local_bytes(root, name)))


def selected_rows(root: Path, config: str) -> Rows:
    """Read exactly en/zh-cn rows 0..3; never search for additional data."""
    if config not in {"en", "zh-cn"}:
        msg = "unselected development config"
        raise ValueError(msg)
    rows = Rows.model_validate_json(local_bytes(root, f"proxy-hf/{config}-train-0-4.json"))
    if tuple(item.row_idx for item in rows.rows) != (0, 1, 2, 3):
        msg = "selected row indices differ"
        raise ValueError(msg)
    return rows


def commons_page(root: Path) -> Page:
    """Require the single supplied page and image revision without following any links."""
    response = CommonsResponse.model_validate_json(local_bytes(root, COMMONS_RAW))
    key = str(COMMONS_PAGEID)
    if tuple(response.query.pages) != (key,):
        msg = "Commons candidate differs"
        raise ValueError(msg)
    page = response.query.pages[key]
    if page.pageid != COMMONS_PAGEID or len(page.revisions) != 1 or len(page.imageinfo) != 1:
        msg = "Commons identity incomplete"
        raise ValueError(msg)
    revision = page.revisions[0]
    if revision.revid != COMMONS_REVID or revision.timestamp != "2026-04-17T15:43:26Z":
        msg = "Commons description revision differs"
        raise ValueError(msg)
    candidates = CandidateResponse.model_validate_json(local_bytes(root, COMMONS_CANDIDATES))
    selected = candidates.query.pages.get(key)
    if selected != CandidatePage.model_validate(page.model_dump()):
        msg = "Commons selected category candidate differs from original metadata"
        raise ValueError(msg)
    return page


def ext_value(info: ImageInfo, name: str) -> str | None:
    """Read a string metadata value without evaluating or rendering its HTML."""
    item = info.extmetadata.get(name)
    if not isinstance(item, dict):
        return None
    value = item.get("value")
    return value if isinstance(value, str) else None
