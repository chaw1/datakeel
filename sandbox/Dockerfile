# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70

RUN pip install --no-cache-dir --no-deps numpy==2.5.4 Pillow==13.0.0
COPY datakeel/sandbox_entry.py /runner/entry.py
COPY datakeel/sandbox_worker.py /runner/worker.py
USER 65532:65532
WORKDIR /output
ENTRYPOINT ["python", "-I", "/runner/entry.py"]
