# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Python license inventory includes selected extras, exact versions, and verified metadata."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, PathDistribution
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from scripts import license_python
from scripts.license_models import LicenseFileEvidence, PythonLock

if TYPE_CHECKING:
    from pathlib import Path


def distribution(tmp_path: Path, license_headers: str, name: str = "generated") -> PathDistribution:
    """Create independent package metadata and a license file without contacting registries."""
    directory = tmp_path / f"{name}-1.0.dist-info"
    directory.mkdir(exist_ok=True)
    (directory / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: 1.0\n" + license_headers + "\n"
    )
    (directory / "LICENSE").write_text("Generated license terms")
    (directory / "RECORD").write_text(f"{name}-1.0.dist-info/LICENSE,,\n")
    return PathDistribution(directory)


def write_lock(tmp_path: Path) -> None:
    """Write a minimal project whose indirect runtime dependency is selected through an extra."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "application"\ndependencies = ["generated[runtime]>=1"]\n'
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "application"\nversion = "1.0"\n'
        'dependencies = [{name = "generated", extra = ["runtime"]}]\n'
        '[[package]]\nname = "generated"\nversion = "1.0"\n'
        '[package.optional-dependencies]\nruntime = [{name = "indirect"}]\n'
        '[[package]]\nname = "indirect"\nversion = "1.0"\n'
    )


def test_runtime_closure_includes_recursive_extras_and_excludes_dev_and_inactive_markers() -> None:
    """Extras reached through different paths merge without including unrelated optional tools."""
    lock = PythonLock.model_validate(
        {
            "package": [
                {
                    "name": "application",
                    "version": "1",
                    "dependencies": [{"name": "runtime", "extra": ["first", "second"]}],
                    "dev-dependencies": {"dev": [{"name": "dev-tool"}]},
                },
                {
                    "name": "runtime",
                    "version": "1",
                    "dependencies": [{"name": "omitted", "marker": "python_version < '1'"}],
                    "optional-dependencies": {
                        "first": [{"name": "nested", "extra": ["active"]}],
                        "second": [{"name": "nested"}],
                        "unused": [{"name": "dev-tool"}],
                    },
                },
                {
                    "name": "nested",
                    "version": "1",
                    "optional-dependencies": {"active": [{"name": "leaf"}]},
                },
                {"name": "leaf", "version": "1", "dependencies": [{"name": "runtime"}]},
                {"name": "dev-tool", "version": "1"},
            ]
        }
    )
    assert [item.name for item in license_python.runtime_closure(lock, "application")] == [
        "leaf",
        "nested",
        "runtime",
    ]


@pytest.mark.parametrize(
    "dependency", [{"name": "missing"}, {"name": "application", "extra": ["missing"]}]
)
def test_runtime_closure_rejects_incomplete_lock_edges(dependency: dict[str, object]) -> None:
    """An incomplete graph fails rather than silently omitting runtime packages."""
    lock = PythonLock.model_validate(
        {"package": [{"name": "application", "version": "1", "dependencies": [dependency]}]}
    )
    with pytest.raises(ValidationError):
        license_python.runtime_closure(lock, "application")


def test_runtime_closure_selects_marker_bound_version_and_rejects_ambiguity() -> None:
    """Universal lock variants are resolved for this interpreter before metadata is read."""
    lock = PythonLock.model_validate(
        {
            "package": [
                {"name": "application", "version": "1", "dependencies": [{"name": "runtime"}]},
                {"name": "runtime", "version": "1", "resolution-markers": ["python_version < '1'"]},
                {
                    "name": "runtime",
                    "version": "2",
                    "resolution-markers": ["python_version >= '1'"],
                },
            ]
        }
    )
    assert license_python.runtime_closure(lock, "application")[0].version == "2"
    duplicate = lock.packages[-1].model_copy(update={"version": "3"})
    with pytest.raises(ValidationError, match="exactly once"):
        license_python.runtime_closure(
            lock.model_copy(update={"packages": (*lock.packages, duplicate)}), "application"
        )


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ("License-Expression: GPL-3.0-only\nLicense: MIT\n", "GPL-3.0-only"),
        ("License: UNKNOWN\nClassifier: License :: OSI Approved :: MIT License\n", "UNKNOWN"),
        ("Classifier: License :: OSI Approved :: MIT License\n", "MIT"),
        ("Classifier: License :: OSI Approved :: BSD License\n", "UNKNOWN"),
        ("Classifier: License :: OSI Approved :: Apache Software License\n", "UNKNOWN"),
        ("License: BSD\n", "BSD"),
        ("License: Apache License 2.0\n", "Apache-2.0"),
        ("License: MIT No Attribution\n", "MIT-0"),
        ("", "UNKNOWN"),
    ],
)
def test_license_metadata_precedence_never_hides_unknown_or_gpl(
    tmp_path: Path, headers: str, expected: str
) -> None:
    """A precise expression takes precedence; generic BSD text is not guessed to be BSD-3."""
    item = distribution(tmp_path, headers)
    assert license_python.declared_license(item)[0] == expected


def test_legacy_license_requires_exact_version_declared_value_and_file_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reviewed source text may disambiguate legacy metadata but cannot excuse changed terms."""
    item = distribution(tmp_path, "License: Dual License\n")
    evidence = LicenseFileEvidence(
        name="generated",
        version="1.0",
        declared="Dual License",
        filename="LICENSE",
        sha256=hashlib.sha256(b"Generated license terms").hexdigest(),
        license="BSD-3-Clause",
    )
    monkeypatch.setattr(license_python, "_LEGACY_EVIDENCE", (evidence,))
    license_id, source = license_python.declared_license(item)
    assert license_id == "BSD-3-Clause"
    assert evidence.sha256 in source
    (tmp_path / "generated-1.0.dist-info" / "LICENSE").write_text("Changed terms")
    assert license_python.declared_license(item)[0] == "Dual License"


def test_legacy_declaration_hash_still_requires_unchanged_metadata_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long metadata declaration is bound by hash without copying upstream personal details."""
    item = distribution(tmp_path, "License: Generated legacy declaration\n")
    evidence = LicenseFileEvidence(
        name="generated",
        version="1.0",
        declared_sha256=hashlib.sha256(b"Generated legacy declaration").hexdigest(),
        filename="LICENSE",
        sha256=hashlib.sha256(b"Generated license terms").hexdigest(),
        license="MIT",
    )
    monkeypatch.setattr(license_python, "_LEGACY_EVIDENCE", (evidence,))
    assert license_python.declared_license(item)[0] == "MIT"
    metadata_path = tmp_path / "generated-1.0.dist-info" / "METADATA"
    original = metadata_path.read_text()
    metadata_path.write_text(original.replace("Generated legacy declaration", "GPL-3.0-only"))
    assert license_python.declared_license(item)[0] == "GPL-3.0-only"
    metadata_path.write_text(original)
    (tmp_path / "generated-1.0.dist-info" / "LICENSE").write_text("Changed terms")
    assert license_python.declared_license(item)[0] == "Generated legacy declaration"


def test_python_inventory_reports_transitive_packages_with_matching_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both a direct package and its selected-extra dependency appear in the inventory."""
    write_lock(tmp_path)
    generated = distribution(
        tmp_path, 'License-Expression: MIT\nRequires-Dist: indirect>=1; extra == "runtime"\n'
    )
    indirect = distribution(tmp_path, "License-Expression: MIT\n", "indirect")

    def installed_distribution(name: str) -> PathDistribution:
        return {"generated": generated, "indirect": indirect}[name]

    monkeypatch.setattr(license_python.metadata, "distribution", installed_distribution)
    result = license_python.python_packages(tmp_path)
    assert [(item.name, item.version, item.license) for item in result] == [
        ("generated", "1.0", "MIT"),
        ("indirect", "1.0", "MIT"),
    ]


def test_python_inventory_rejects_missing_installation_and_lock_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing or stale installed distributions cannot yield an incomplete green report."""
    write_lock(tmp_path)

    def missing(name: str) -> PathDistribution:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(license_python.metadata, "distribution", missing)
    with pytest.raises(ValidationError, match="not installed"):
        license_python.python_packages(tmp_path)
    installed = distribution(tmp_path, "License-Expression: MIT\n")
    metadata_path = tmp_path / "generated-1.0.dist-info" / "METADATA"
    metadata_path.write_text(metadata_path.read_text().replace("Version: 1.0", "Version: 2.0"))

    def installed_distribution(_name: str) -> PathDistribution:
        return installed

    monkeypatch.setattr(license_python.metadata, "distribution", installed_distribution)
    with pytest.raises(ValidationError, match=r"differs from uv\.lock"):
        license_python.python_packages(tmp_path)


@pytest.mark.parametrize("identity", ["Name: different-package", "Name:"])
def test_python_inventory_rejects_wrong_or_missing_installed_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, identity: str
) -> None:
    """A matching version cannot lend one distribution's license to a different locked package."""
    write_lock(tmp_path)
    installed = distribution(tmp_path, "License-Expression: MIT\n")
    metadata_path = tmp_path / "generated-1.0.dist-info" / "METADATA"
    metadata_path.write_text(metadata_path.read_text().replace("Name: generated", identity))

    def installed_distribution(_name: str) -> PathDistribution:
        return installed

    monkeypatch.setattr(license_python.metadata, "distribution", installed_distribution)
    with pytest.raises(ValidationError, match="Installed identity differs"):
        license_python.python_packages(tmp_path)


@pytest.mark.parametrize(
    "requirement",
    [
        "",
        "Requires-Dist: unlocked-copyleft>=1\n",
        'Requires-Dist: indirect>=2; extra == "runtime"\n',
        'Requires-Dist: indirect[hidden]>=1; extra == "runtime"\n',
        'Requires-Dist: indirect>=1; extra == "unselected"\n',
        "Requires-Dist: indirect @ https://example.invalid/indirect.whl\n",
        "Requires-Dist: not a requirement\n",
    ],
)
def test_python_inventory_rejects_changed_installed_runtime_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requirement: str
) -> None:
    """Missing, added, malformed, extra-dependent, or incompatible installed edges fail closed."""
    write_lock(tmp_path)
    installed = distribution(tmp_path, "License-Expression: MIT\n" + requirement)

    def installed_distribution(_name: str) -> PathDistribution:
        return installed

    monkeypatch.setattr(license_python.metadata, "distribution", installed_distribution)
    with pytest.raises(ValidationError, match=r"[Rr]untime"):
        license_python.python_packages(tmp_path)


def test_python_inventory_ignores_inactive_extra_and_platform_requirements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Canonical names match while unselected development extras and inactive platforms stay out."""
    write_lock(tmp_path)
    generated = distribution(
        tmp_path,
        'License-Expression: MIT\nRequires-Dist: INDIRECT>=1; extra == "runtime"\n'
        'Requires-Dist: inactive-copyleft; python_version < "1"\n'
        'Requires-Dist: dev-copyleft; extra == "development"\n',
        "Generated",
    )
    indirect = distribution(tmp_path, "License-Expression: MIT\n", "indirect")

    def installed_distribution(name: str) -> PathDistribution:
        return {"generated": generated, "indirect": indirect}[name]

    monkeypatch.setattr(license_python.metadata, "distribution", installed_distribution)
    assert [item.name for item in license_python.python_packages(tmp_path)] == [
        "generated",
        "indirect",
    ]


@pytest.mark.parametrize("requirement", ["replacement", "generated", "generated[runtime]>=2"])
def test_python_inventory_rejects_project_dependency_drift(
    tmp_path: Path, requirement: str
) -> None:
    """A changed project declaration cannot silently audit a stale lock's old runtime roots."""
    write_lock(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "application"\ndependencies = ["{requirement}"]\n'
    )
    with pytest.raises(ValidationError, match=r"uv\.lock"):
        license_python.python_packages(tmp_path)
