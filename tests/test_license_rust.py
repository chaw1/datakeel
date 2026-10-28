# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rust auditing fails closed and preserves every selected crate's upstream notices."""

from pathlib import Path

import pytest

from datakeel.core.errors import ValidationError
from scripts import license_rust
from scripts.license_rust import (
    CargoMetadata,
    CargoNode,
    CargoPackage,
    CargoResolve,
    metadata_packages,
    render_rust_notices,
    rust_packages,
)


def _metadata(root: Path, license_id: str | None = "MIT") -> CargoMetadata:
    return CargoMetadata(
        packages=(
            CargoPackage(
                id="root",
                name="datakeel-accel",
                version="0.1.0",
                license="Apache-2.0",
                manifest_path=root / "accel/Cargo.toml",
            ),
            CargoPackage(
                id="dependency",
                name="fixture-crate",
                version="1.0.0",
                license=license_id,
                manifest_path=root / "registry/fixture-crate/Cargo.toml",
            ),
            CargoPackage(
                id="unselected",
                name="unselected-crate",
                version="2.0.0",
                license="GPL-3.0-only",
                manifest_path=root / "registry/unselected/Cargo.toml",
            ),
        ),
        resolve=CargoResolve(
            root="root",
            nodes=(
                CargoNode(id="root", dependencies=("dependency",)),
                CargoNode(id="dependency", dependencies=()),
                CargoNode(id="unselected", dependencies=()),
            ),
        ),
    )


def test_metadata_closure_excludes_root_and_unselected_packages(tmp_path: Path) -> None:
    """Include only the resolved root's exact dependency closure, retaining full SPDX."""
    packages = metadata_packages(_metadata(tmp_path, "MIT OR Apache-2.0"))
    assert [(item.name, item.version, item.license) for item in packages] == [
        ("fixture-crate", "1.0.0", "MIT OR Apache-2.0")
    ]
    assert all(item.ecosystem == "rust" for item in packages)
    assert str(tmp_path) not in packages[0].evidence


def test_metadata_missing_license_remains_unknown(tmp_path: Path) -> None:
    """Never infer a permitted license when the locked crate declaration is absent."""
    assert metadata_packages(_metadata(tmp_path, None))[0].license == "UNKNOWN"


def test_metadata_unresolved_transitive_identity_fails(tmp_path: Path) -> None:
    """A truncated graph must fail rather than omit an unaudited dependency."""
    metadata = _metadata(tmp_path)
    broken = metadata.model_copy(
        update={
            "resolve": CargoResolve(
                root="root",
                nodes=(CargoNode(id="root", dependencies=("missing",)),),
            )
        }
    )
    with pytest.raises(ValidationError, match="unresolved dependency"):
        metadata_packages(broken)


def test_rust_packages_requires_lockfile(tmp_path: Path) -> None:
    """Source auditing cannot silently resolve an unlocked dependency tree."""
    with pytest.raises(ValidationError, match=r"Cargo\.lock is required"):
        rust_packages(tmp_path)


def test_rust_packages_rejects_metadata_not_in_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An installed crate with a different version cannot supply license evidence."""
    (tmp_path / "accel").mkdir()
    (tmp_path / "accel/Cargo.lock").write_text(
        '[[package]]\nname = "fixture-crate"\nversion = "0.9.0"\n'
    )
    monkeypatch.setattr(license_rust, "_metadata", lambda _root: _metadata(tmp_path))
    with pytest.raises(ValidationError, match="identity differs"):
        rust_packages(tmp_path)


def test_rust_packages_accepts_exact_locked_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind the selected source's license metadata to the committed Cargo version."""
    (tmp_path / "accel").mkdir()
    (tmp_path / "accel/Cargo.lock").write_text(
        '[[package]]\nname = "fixture-crate"\nversion = "1.0.0"\n'
    )
    monkeypatch.setattr(license_rust, "_metadata", lambda _root: _metadata(tmp_path))
    assert rust_packages(tmp_path)[0].name == "fixture-crate"


def test_missing_cargo_reports_installation_instructions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate must explain the required toolchain instead of skipping Rust auditing."""
    monkeypatch.setattr(license_rust.shutil, "which", lambda _name: None)
    with pytest.raises(ValidationError, match="install Rust with rustup"):
        license_rust._metadata(tmp_path)  # noqa: SLF001  # Exercise the process boundary.


def test_upstream_notices_preserved_without_registry_paths(tmp_path: Path) -> None:
    """Ship every selected license/notice byte, excluding local source path metadata."""
    source = tmp_path / "registry/fixture-crate"
    source.mkdir(parents=True)
    license_text = "Copyright fixture contributors\n\nPermission is granted.\n"
    notice_text = "Additional attribution must remain intact.\n"
    (source / "LICENSE-MIT").write_text(license_text)
    (source / "NOTICE").write_text(notice_text)
    rendered = render_rust_notices(_metadata(tmp_path))
    assert license_text in rendered
    assert notice_text in rendered
    assert "fixture-crate 1.0.0" in rendered
    assert "unselected-crate" not in rendered
    assert str(tmp_path) not in rendered


def test_missing_upstream_license_text_fails_distribution(tmp_path: Path) -> None:
    """A metadata SPDX declaration alone cannot replace redistribution notices."""
    with pytest.raises(ValidationError, match="no upstream license text"):
        render_rust_notices(_metadata(tmp_path))
