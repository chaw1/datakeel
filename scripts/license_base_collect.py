# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Collect installed image license evidence with the Python standard library only."""

import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
import sysconfig
from pathlib import Path


def _evidence(path: Path) -> dict[str, str]:
    content = path.read_bytes()
    if not content.strip():
        msg = "An installed dependency has no copyright/license evidence"
        raise ValueError(msg)
    return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest()}


def _os_packages() -> list[dict[str, object]]:
    result = subprocess.run(
        [
            "/usr/bin/dpkg-query",
            "--show",
            "--showformat=${binary:Package}\t${Version}\t${Architecture}\n",
        ],
        capture_output=True,
        check=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C"},
    )
    packages: list[dict[str, object]] = []
    for line in result.stdout.decode().splitlines():
        package, version, architecture = line.split("\t")
        name = package.split(":", 1)[0]
        path = Path("/usr/share/doc") / name / "copyright"
        evidence = _evidence(path)
        content = path.read_text(errors="replace")
        declared = re.findall(r"^License:\s*(.+)$", content, re.MULTILINE)
        declared += re.findall(r"/usr/share/common-licenses/([A-Za-z0-9.+-]+)", content)
        licenses = sorted(set(declared)) or ["LicenseRef-Upstream-Copyright"]
        packages.append(
            {
                "name": name,
                "version": version,
                "architecture": architecture,
                "copyright": evidence,
                "licenses": licenses,
            }
        )
    return sorted(packages, key=lambda package: str(package["name"]))


def _python_packages() -> list[dict[str, object]]:
    packages: list[dict[str, object]] = []
    for distribution in importlib.metadata.distributions():
        evidence = []
        for file in distribution.files or ():
            if file.name.lower().startswith(("license", "copying")):
                path = Path(distribution.locate_file(file))
                if path.is_file():
                    evidence.append(_evidence(path))
        if not evidence:
            msg = "An installed Python package has no license file"
            raise ValueError(msg)
        declared = (
            distribution.metadata.get("License-Expression")
            or distribution.metadata.get("License")
            or "LicenseRef-Upstream-Copyright"
        )
        packages.append(
            {
                "name": distribution.metadata["Name"],
                "version": distribution.version,
                "license": declared,
                "evidence": sorted(evidence, key=lambda item: item["path"]),
            }
        )
    return sorted(packages, key=lambda package: str(package["name"]).lower())


def main() -> None:
    """Emit metadata only; never disclose application environment or host paths."""
    value = {
        "python": {
            "version": sys.version.split()[0],
            "license": "PSF-2.0",
            "evidence": _evidence(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"),
        },
        "python_packages": _python_packages(),
        "os_packages": _os_packages(),
    }
    sys.stdout.write(json.dumps(value, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
