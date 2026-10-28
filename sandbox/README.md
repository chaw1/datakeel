# Sandbox image license inventory

The image uses the official Python slim base pinned in `Dockerfile`. Its Python
interpreter and base tooling, installed numpy/Pillow wheels, and every installed
Debian package are recorded in `BASE_IMAGE_INVENTORY.json`. Each dependency has
its installed version and retained upstream copyright/license file path and
SHA-256. The inventory identifies the measured Linux architecture and immutable
image digest; the base reference identifies the fixed multi-architecture image.

The regular license gate checks the Dockerfile base reference, complete evidence
fields and package count, locked numpy/Pillow versions, and the actual interpreter
and wheel license expressions. Python additions remain under the existing
permissive policy. Debian package declarations belong to the official operating
system distribution and are recorded separately, including GPL/LGPL and other
upstream terms. No Python allowlist exception is introduced. A legacy
`LicenseRef-Upstream-Copyright` identifier points to the exact retained copyright
text rather than claiming an unverified SPDX license. These unchanged upstream
notices remain inside the image.

To regenerate from an already-local image built from the current Dockerfile:

```sh
docker build -f sandbox/Dockerfile -t datakeel-sandbox-local .
uv run python -m scripts.generate_base_inventory \
  --image "$(docker image inspect datakeel-sandbox-local --format '{{.Id}}')"
```

The collector uses only Python's standard library inside a disposable nonroot,
read-only container with no network, no extra host mounts, and bounded resources.
It never pulls images. It accepts only an existing image with a
`datakeel-sandbox-` tag and removes only its exact container after checking the
per-run ownership label. The checked inventory currently measures Linux arm64;
other architectures can reproduce their own inventory using the same command.
