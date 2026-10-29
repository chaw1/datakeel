# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic normalized fingerprints and bounded-cost similarity measurements."""

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

import numpy as np

_SEEDS = np.array(
    [
        0x9E3779B185EBCA87,
        0xC2B2AE3D27D4EB4F,
        0x165667B19E3779F9,
        0x85EBCA77C2B2AE63,
        0x27D4EB2F165667C5,
        0x94D049BB133111EB,
        0xBF58476D1CE4E5B9,
        0xD6E8FEB86659FD93,
        0xA0761D6478BD642F,
        0xE7037ED1A0B428DB,
        0x8EBC6AF09C88C6E3,
        0x589965CC75374CC3,
        0x1D8E4E27C47D124F,
        0xEB44ACCAB455D165,
        0xDB4F0B9175AE2165,
        0xBBE0563303A4615F,
    ],
    dtype=np.uint64,
)
_MAX_FEATURES = 512
_MAX_CACHED_TEXT = 4096
_SHORT_TEXT = 256
_MIN_LENGTH_RATIO = 0.75
MIN_LENGTH_RATIO = _MIN_LENGTH_RATIO
SHORT_TEXT_LENGTH = _SHORT_TEXT
_MIN_SHINGLE_OVERLAP = 0.5
_NON_ALNUM = re.compile(r"[\W_]+")


def normalize(text: str) -> str:
    """Ignore Unicode width, case, whitespace and punctuation for exact duplicate identity."""
    return _NON_ALNUM.sub("", unicodedata.normalize("NFKC", text).casefold())


def digest(text: str) -> bytes:
    """Hash normalized content into an immutable, fixed-width index key."""
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()


def shingles(text: str, size: int = 3) -> set[str]:
    """Return character shingles, with a single short-text feature where necessary."""
    return {text[offset : offset + size] for offset in range(max(1, len(text) - size + 1))}


@lru_cache(maxsize=65536)
def _feature_hash(feature: str) -> bytes:
    return hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()


def fingerprint(text: str) -> tuple[int, tuple[bytes, ...]]:
    """Build a 64-bit SimHash and eight two-value MinHash bands using existing NumPy."""
    features = shingles(text)
    # Lexical sampling bounds long-line work independently of hash randomization.
    selected = sorted(features)[:_MAX_FEATURES]
    values = np.frombuffer(
        b"".join(_feature_hash(feature) for feature in selected), dtype=np.uint64
    )
    bits = np.unpackbits(values.view(np.uint8)).reshape(-1, 64).sum(axis=0)
    simhash = int.from_bytes(np.packbits(bits * 2 >= len(values)).tobytes(), "little")
    mixed = values[:, None] * _SEEDS + (_SEEDS >> np.uint64(1))
    minima = mixed.min(axis=0)
    bands = tuple(
        bytes([offset]) + minima[offset : offset + 2].tobytes() for offset in range(0, 16, 2)
    )
    return simhash, bands


@lru_cache(maxsize=256)
def _cached_shingles(text: str) -> frozenset[str]:
    return frozenset(shingles(text))


def _similarity_shingles(text: str) -> frozenset[str]:
    # Bound both the number and size of retained entries, including custom line limits.
    if len(text) <= _MAX_CACHED_TEXT:
        return _cached_shingles(text)
    return frozenset(shingles(text))


def similarity(left: str, right: str) -> float:
    """Confirm LSH candidates using edits for short text and shingle Dice for longer text."""
    if left == right:
        return 1
    if min(len(left), len(right)) / max(1, len(left), len(right)) < _MIN_LENGTH_RATIO:
        return 0
    left_set, right_set = _similarity_shingles(left), _similarity_shingles(right)
    dice = 2 * len(left_set & right_set) / max(1, len(left_set) + len(right_set))
    if max(len(left), len(right)) <= _SHORT_TEXT:
        if dice < _MIN_SHINGLE_OVERLAP:
            return dice
        return SequenceMatcher(None, left, right, autojunk=False).ratio()
    return dice


def tokens(text: str) -> tuple[str, ...]:
    """Use words for Latin scripts and characters for Chinese evaluation n-grams."""
    return tuple(
        re.findall(r"[\u3400-\u9fff]|[^\W_]+", unicodedata.normalize("NFKC", text).casefold())
    )
