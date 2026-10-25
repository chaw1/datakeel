# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject unapproved codec libraries hidden inside an otherwise permissive OpenCV wheel."""

from __future__ import annotations

from importlib import import_module, metadata
from typing import Protocol, cast

from scripts.license_models import LicenseFinding

_RESTRICTED_LIBRARIES = (
    "ffmpeg",
    "gstreamer",
    "avcodec",
    "avdevice",
    "avfilter",
    "avformat",
    "avutil",
    "swresample",
    "swscale",
    "postproc",
    "x264",
    "x265",
    "unistring",
    "gmp",
    "gnutls",
    "glib-",
    "intl.",
    "bluray",
    "rubberband",
    "vidstab",
)


class _OpenCV(Protocol):
    def getBuildInformation(self) -> str: ...  # noqa: N802  # Upstream public API.


def native_findings() -> tuple[LicenseFinding, ...]:
    """Inspect both installed library filenames and runtime-reported video support."""
    distribution = metadata.distribution("opencv-python-headless")
    libraries = tuple(
        str(file)
        for file in distribution.files or ()
        if (file.suffix in {".dylib", ".dll"} or ".so" in file.name)
        and any(name in file.name.lower() for name in _RESTRICTED_LIBRARIES)
    )
    build = cast("_OpenCV", import_module("cv2")).getBuildInformation()
    video = any(
        "YES" in line and ("FFMPEG:" in line or "GStreamer:" in line) for line in build.splitlines()
    )
    if not libraries and not video:
        return ()
    return (
        LicenseFinding(
            ecosystem="python",
            name="opencv-python-headless",
            version=distribution.version,
            license="LGPL-2.1-or-later / unapproved bundled video libraries",
            reason=(
                "The installed wheel includes unapproved video libraries; rebuild OpenCV with "
                "FFmpeg, GStreamer and videoio disabled. Observed libraries: "
                + ", ".join(libraries)
            ),
        ),
    )
