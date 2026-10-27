# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check the generated recording's defects and microphone synchronization."""

from pathlib import Path

import numpy as np

from datakeel.core.models import FileItem
from datakeel.operators.media.align import OPERATOR
from datakeel.operators.media.tools import decode_audio, probe_file, run_tool, run_tool_stderr
from datakeel.sample_media import generate_media


def test_generator_lavfi_recordings_contain_expected_defects(tmp_path: Path) -> None:
    """Measure the intended defects independently with ffmpeg and sample energy."""
    sources = generate_media(tmp_path)
    camera = FileItem(path=str(sources / "camera.mkv"), filename="camera.mkv", modality="video")
    microphone = FileItem(
        path=str(sources / "external-microphone.wav"),
        filename="external-microphone.wav",
        modality="audio",
    )
    assert probe_file(camera).duration_ms == 12000
    assert probe_file(microphone).duration_ms == 12500
    assert (sources / "camera-copy.mkv").read_bytes() == Path(camera.path).read_bytes()
    diagnostics = run_tool_stderr(
        [
            "ffmpeg",
            "-i",
            camera.path,
            "-vf",
            "blackdetect=d=0.5,freezedetect=n=-50dB:d=1",
            "-an",
            "-f",
            "null",
            "-",
        ]
    ).decode()
    assert "black_start:0" in diagnostics
    assert "freeze_start: 4" in diagnostics
    frames = np.frombuffer(
        run_tool(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                camera.path,
                "-vf",
                "fps=1",
                "-pix_fmt",
                "gray",
                "-f",
                "rawvideo",
                "pipe:1",
            ]
        ),
        dtype=np.uint8,
    ).reshape(12, 120, 160)
    assert np.array_equal(frames[1:4], frames[6:9])
    samples = decode_audio(camera)
    assert float(np.mean(samples[4 * 16000 : 6 * 16000] ** 2)) < 1e-8
    assert float(np.mean(samples[16000 : 3 * 16000] ** 2)) > 1e-6
    aligned = OPERATOR.run([camera, microphone], tmp_path / "output")
    assert aligned.files[1].metadata["media_alignment"]["offset_ms"] == 500
