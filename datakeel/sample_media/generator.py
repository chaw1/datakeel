# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate small, reproducible recordings from local lavfi signal sources."""

from pathlib import Path
from shutil import copyfile

from datakeel.operators.media.tools import run_tool

_VIDEO_FILTER = (
    "[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0[video];"
    "[5:a]aeval='if(between(t,4,6),0,val(0))'[audio]"
)


def _camera(path: Path) -> None:
    run_tool(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x120:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=30:d=3",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=30:d=0.033333,tpad=stop_mode=clone:stop_duration=1.966667",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=30:d=3",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=30:d=6,trim=start=3:end=6,setpts=PTS-STARTPTS",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=pink:sample_rate=16000:duration=12:amplitude=0.2:seed=613",
            "-filter_complex",
            _VIDEO_FILTER,
            "-map",
            "[video]",
            "-map",
            "[audio]",
            "-c:v",
            "ffv1",
            "-threads",
            "1",
            "-c:a",
            "pcm_s16le",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            str(path),
        ]
    )


def generate_media(directory: Path) -> Path:
    """Write a camera, its duplicate and a microphone delayed by 500 ms.

    The 12-second camera contains black video at 0-1 seconds, a held frame at
    4-6 seconds, repeated moving content at 1-4 and 6-9 seconds, and silence at
    4-6 seconds. All source media is generated locally from lavfi sources.

    Args:
        directory: User-selected destination for the generated dataset.

    Returns:
        The source directory to import into Datakeel.
    """
    sources = directory / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    camera = sources / "camera.mkv"
    _camera(camera)
    copyfile(camera, sources / "camera-copy.mkv")
    run_tool(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(camera),
            "-vn",
            "-af",
            "adelay=500:all=1",
            "-c:a",
            "pcm_s16le",
            "-fflags",
            "+bitexact",
            str(sources / "external-microphone.wav"),
        ]
    )
    return sources
