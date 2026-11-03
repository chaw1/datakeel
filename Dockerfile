# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70

COPY dist/requirements.txt /tmp/requirements.txt
COPY dist/datakeel-*.whl /tmp/wheels/
RUN pip install --no-cache-dir --require-hashes --requirement /tmp/requirements.txt \
    && wheel=$(find /tmp/wheels -name 'datakeel-*.whl' -print -quit) \
    && pip install --no-cache-dir --no-deps "$wheel" \
    && rm -rf /tmp/requirements.txt /tmp/wheels
RUN useradd --uid 65532 --create-home datakeel \
    && mkdir /data \
    && chown datakeel:datakeel /data
USER 65532:65532
ENV DATAKEEL_HOME=/data
EXPOSE 8765
ENTRYPOINT ["datakeel"]
CMD ["api", "--host", "0.0.0.0", "--port", "8765"]
