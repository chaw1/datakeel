# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive row identities and conservative license decisions from saved public inputs."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import TYPE_CHECKING
from urllib.parse import quote

from PIL import Image

from scripts.we_e1.generate import canonical
from scripts.we_e1.models import Boundary, EvidenceFile, PublicRow, RowMetadata, SourceRegistry
from scripts.we_e1.preprocess import sha256
from scripts.we_e1.public_inputs import (
    COMMONS_JPG,
    COMMONS_RAW,
    DatasetAPI,
    IndexedRow,
    commons_page,
    evidence,
    ext_value,
    local_bytes,
    selected_rows,
)
from scripts.we_e1.public_models import LicenseLedger, LicenseRecord

if TYPE_CHECKING:
    from pathlib import Path

CC = "https://creativecommons.org/licenses/by-sa/4.0/"
TEXT_OBLIGATIONS = (
    "Attribute Wikipedia contributors with article/history links and retain notices.",
    "Link CC BY-SA 4.0 and indicate upstream extraction and every local modification.",
    "Share adapted text under CC BY-SA 4.0; impose no additional restrictions.",
)


class SourceBundle(Boundary):
    """Return typed sources and ledger together with deterministic derived file bytes."""

    registry: SourceRegistry
    ledger: LicenseLedger
    files: dict[str, bytes]


def _retain(files: dict[str, bytes], name: str, data: bytes) -> EvidenceFile:
    files[name] = data
    return EvidenceFile(path=name, sha256=sha256(data))


def _wiki_row(root: Path, config: str, item: IndexedRow, revision: str) -> RowMetadata:
    row = item.row
    language = "en" if config == "en" else "zh"
    title = row.text.split("\n_START_ARTICLE_\n", 1)[1].split("\n", 1)[0]
    article = f"https://{language}.wikipedia.org/wiki/{quote(title, safe='')}"
    history = (
        f"https://{language}.wikipedia.org/w/index.php?title={quote(title, safe='')}&action=history"
    )
    return RowMetadata(
        stable_id=f"hf:google/wiki40b@{revision}/{config}/train/{item.row_idx}",
        revision=revision,
        license_id="CC-BY-SA-4.0",
        license_url=CC,
        attribution=(
            f"Wikipedia contributors, {title}; {article}; history: {history}. "
            f"Via Google Wiki-40B {config}/train row {item.row_idx}, "
            f"wikidata {row.wikidata_id}, opaque version_id {row.version_id}. "
            "CC BY-SA 4.0; upstream extracted/cleaned text; local changes in license ledger."
        ),
        author="Wikipedia contributors (article history linked; individual editors not enumerated)",
        original_url=f"https://huggingface.co/datasets/google/wiki40b/tree/{revision}/{config}",
        raw_upstream=evidence(root, f"proxy-hf/{config}-train-0-4.json"),
        dataset_revision=revision,
        config=config,
        split="train",
        row_index=item.row_idx,
        wikidata_id=row.wikidata_id,
        version_id=row.version_id,
    )


def _wiki_license(root: Path, meta: RowMetadata) -> LicenseRecord:
    return LicenseRecord(
        stable_id=meta.stable_id,
        license_id=meta.license_id,
        license_url=meta.license_url,
        dataset_card_license="not_declared_More_Information_Needed",
        basis="Underlying Wikipedia text CC BY-SA 4.0; NOT a license grant by the Wiki-40B card.",
        attribution=meta.attribution,
        obligations=TEXT_OBLIGATIONS,
        modifications=(
            "Upstream Wiki-40B extraction/cleaning and structural markers retained verbatim.",
            "original: exact row.text UTF-8; spacing-v1: append two ASCII spaces.",
        ),
        evidence=tuple(
            evidence(root, f"proxy-hf/{name}")
            for name in ("wiki40b-card.md", "wikipedia-copyrights.html", "cc-by-sa-4.0.html")
        ),
        eligible=True,
        limitations=(
            (
                "Mainline supplied selected rows; response has no embedded repository revision. "
                "Snapshot is locally hash-bound to API revision; independent source review pending."
            ),
            "version_id is opaque Wiki-40B data, NOT a verified Wikipedia oldid.",
            "Article title/history links are derived from row text, not fetched article revisions.",
        ),
    )


def _public_row(meta: RowMetadata, original: EvidenceFile, metadata: EvidenceFile) -> PublicRow:
    group = f"wikidata:{meta.wikidata_id}" if meta.wikidata_id else "scene:interior-lighting"
    return PublicRow(
        stable_id=meta.stable_id,
        revision=meta.revision,
        original_sha256=original.sha256,
        original_file=original,
        semantic_group=group,
        near_duplicate_cluster=group,
        transformation_family=f"original-descendants:{group}",
        attribution=meta.attribution,
        license_id=meta.license_id,
        license_url=meta.license_url,
        metadata=metadata,
    )


def _commons_metadata(root: Path) -> RowMetadata:
    page = commons_page(root)
    info = page.imageinfo[0]
    raw = local_bytes(root, COMMONS_JPG)
    if len(raw) != info.size or hashlib.sha1(raw, usedforsecurity=False).hexdigest() != info.sha1:
        msg = "Commons original size/SHA1 disagrees with imageinfo"
        raise ValueError(msg)
    with Image.open(BytesIO(raw)) as image:
        if image.size != (info.width, info.height):
            msg = "Commons original dimensions disagree with imageinfo"
            raise ValueError(msg)
    expected = {
        "LicenseShortName": "CC0",
        "License": "cc0",
        "LicenseUrl": "http://creativecommons.org/publicdomain/zero/1.0/deed.en",
        "UsageTerms": "Creative Commons Zero, Public Domain Dedication",
        "AttributionRequired": "false",
        "Copyrighted": "True",
        "Restrictions": "",
        "Categories": "CC-Zero|Self-published work|Interior lighting",
    }
    if any(ext_value(info, name) != value for name, value in expected.items()):
        msg = "Commons CC0 declaration, LicenseUrl, categories or restrictions differ"
        raise ValueError(msg)
    revid = page.revisions[0].revid
    return RowMetadata(
        stable_id=f"commons:pageid:{page.pageid}:revid:{revid}",
        revision=str(revid),
        license_id="CC0-1.0",
        license_url=ext_value(info, "LicenseUrl"),
        attribution=(
            "Accusedtoppat, ! Bright Lights Ceiling !, own work (2024-09-20). "
            f"https://commons.wikimedia.org/w/index.php?oldid={revid}. "
            "CC0 1.0 Public Domain Dedication; local changes in license ledger."
        ),
        author=ext_value(info, "Artist") or "",
        original_url=info.url,
        raw_upstream=evidence(root, COMMONS_RAW),
        pageid=page.pageid,
        revid=revid,
        imageinfo=tuple(info.model_dump(mode="json") for info in page.imageinfo),
        extmetadata=info.extmetadata,
        license_short_name=ext_value(info, "LicenseShortName"),
        upstream_license_url=ext_value(info, "LicenseUrl"),
    )


def _commons_license(root: Path, meta: RowMetadata) -> LicenseRecord:
    return LicenseRecord(
        stable_id=meta.stable_id,
        license_id=meta.license_id,
        license_url=meta.license_url,
        dataset_card_license=None,
        basis="Per-file CC0 declaration, explicit LicenseUrl, CC-Zero category; no restrictions.",
        attribution=meta.attribution,
        obligations=(
            "CC0 requires no attribution; retain creator, source and modification provenance.",
        ),
        modifications=(
            "original: exact downloaded JPG bytes, no rewrite.",
            "prepared-png-v1: EXIF transpose, RGB, max side 512, metadata stripped.",
            "mirror-png-v1: horizontal mirror of prepared image; no semantic gold asserted.",
        ),
        evidence=(evidence(root, COMMONS_RAW),),
        eligible=True,
        limitations=(
            "Copyrighted=True is preserved alongside the explicit CC0 dedication, not rewritten.",
            "Local checks do not replace independent per-file source/license review.",
        ),
    )


def _check_text_evidence(root: Path) -> None:
    checks = (
        ("wiki40b-card.md", "### Licensing Information\n\n[More Information Needed]"),
        ("wikipedia-copyrights.html", "creativecommons.org/licenses/by-sa/4.0"),
        ("cc-by-sa-4.0.html", "ShareAlike"),
        ("cc-by-sa-4.0.html", "appropriate credit"),
    )
    for name, marker in checks:
        if marker not in local_bytes(root, f"proxy-hf/{name}").decode("utf-8"):
            msg = "expected upstream license/card statement missing"
            raise ValueError(msg)


def build_sources(root: Path) -> SourceBundle:
    """Build nine locally eligible originals; independent review stays pending."""
    _check_text_evidence(root)
    api = DatasetAPI.model_validate_json(local_bytes(root, "proxy-hf/wiki40b-api.json"))
    files: dict[str, bytes] = {}
    rows: list[PublicRow] = []
    licenses: list[LicenseRecord] = []
    for config in ("en", "zh-cn"):
        for item in selected_rows(root, config).rows:
            name = f"derived/wiki40b-{config}-{item.row_idx}"
            meta = _wiki_row(root, config, item, api.sha)
            original = _retain(files, name + ".txt", item.row.text.encode("utf-8"))
            metadata = _retain(
                files, name + ".metadata.json", canonical(meta.model_dump(mode="json"))
            )
            rows.append(_public_row(meta, original, metadata))
            licenses.append(_wiki_license(root, meta))
    meta = _commons_metadata(root)
    metadata = _retain(
        files, "derived/commons-152924098.metadata.json", canonical(meta.model_dump(mode="json"))
    )
    rows.append(_public_row(meta, evidence(root, COMMONS_JPG), metadata))
    licenses.append(_commons_license(root, meta))
    ledger = LicenseLedger(records=tuple(licenses))
    registry = _registry(api.sha, tuple(rows), ledger)
    return SourceBundle(registry=registry, ledger=ledger, files=files)


def _registry(revision: str, rows: tuple[PublicRow, ...], ledger: LicenseLedger) -> SourceRegistry:
    return SourceRegistry.model_validate_json(
        canonical(
            {
                "contract_version": "we-e1-v1",
                "network_performed": True,
                "sources": [
                    {
                        "source_id": source,
                        "planned_url": url,
                        "status": "frozen" if record.eligible else "blocked",
                        "revision": revision if source == "wiki40b-style" else rows[-1].revision,
                        "rows": [r.model_dump(mode="json") for r in selected],
                        "license_evidence": [e.model_dump() for e in record.evidence],
                        "blockers": [] if record.eligible else list(record.limitations),
                    }
                    for source, url, selected, record in (
                        (
                            "wiki40b-style",
                            "https://huggingface.co/datasets/google/wiki40b",
                            rows[:-1],
                            ledger.records[0],
                        ),
                        (
                            "wikimedia-commons",
                            "https://commons.wikimedia.org/",
                            rows[-1:],
                            ledger.records[-1],
                        ),
                    )
                ],
            }
        )
    )
