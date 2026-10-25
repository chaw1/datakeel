#!/bin/sh
# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

# Install the locked OCR extra into an explicit environment, rebuilding OpenCV without video.
set -eu
if [ "$#" -ne 1 ]; then
    echo "Usage: scripts/install_ocr.sh /absolute/path/to/ocr-environment" >&2
    exit 2
fi
ocr_environment="$1"
ocr_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ocr_root"
UV_PROJECT_ENVIRONMENT="$ocr_environment" uv sync --locked --extra ocr --no-dev
ocr_python="$ocr_environment/bin/python"
opencv_version=$("$ocr_python" -c 'from importlib.metadata import version; print(version("opencv-python-headless"))')
# RapidOCR consumes arrays; image transforms need no video support. Calibration/features keep upstream stub generation valid.
ENABLE_HEADLESS=1 \
CMAKE_BUILD_PARALLEL_LEVEL=4 \
CMAKE_ARGS='-DWITH_FFMPEG=OFF -DWITH_GSTREAMER=OFF -DBUILD_opencv_videoio=OFF -DWITH_OPENEXR=OFF -DWITH_TIFF=OFF -DWITH_WEBP=OFF -DWITH_JASPER=OFF -DWITH_OPENJPEG=OFF -DWITH_AVIF=OFF -DWITH_TBB=OFF -DWITH_IPP=OFF -DWITH_EIGEN=OFF -DWITH_OPENCL=OFF -DBUILD_LIST=core,imgproc,imgcodecs,features,calib,python3 -DBUILD_JPEG=ON -DBUILD_PNG=ON -DBUILD_ZLIB=ON -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF' \
uv pip install --python "$ocr_python" --no-cache --no-deps \
    --no-binary opencv-python-headless --reinstall-package opencv-python-headless \
    "opencv-python-headless==$opencv_version"
"$ocr_python" -m scripts.license_ocr --root "$ocr_root"
