# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frontend inventories resolve production transitive dependencies and exact installed metadata."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from scripts.license_audit import license_findings
from scripts.license_bundle import source_hash
from scripts.license_frontend import frontend_packages, production_closure
from scripts.license_models import BundleInventory, FrontendLock, FrontendPackage

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue


def test_production_closure_resolves_nested_dependencies_peers_and_optional_packages() -> None:
    """A nested version wins over a hoisted one and unrelated dev packages stay excluded."""
    lock = FrontendLock.model_validate(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"runtime": "1"}, "devDependencies": {"dev-tool": "1"}},
                "node_modules/runtime": {
                    "dependencies": {"nested": "1"},
                    "peerDependencies": {"peer": "1", "absent-peer": "1"},
                    "peerDependenciesMeta": {"absent-peer": {"optional": True}},
                    "optionalDependencies": {"optional": "1", "absent-optional": "1"},
                },
                "node_modules/runtime/node_modules/nested": {"dependencies": {"runtime": "1"}},
                "node_modules/nested": {},
                "node_modules/peer": {},
                "node_modules/optional": {},
                "node_modules/dev-tool": {},
            },
        }
    )
    assert production_closure(lock) == (
        "node_modules/optional",
        "node_modules/peer",
        "node_modules/runtime",
        "node_modules/runtime/node_modules/nested",
    )


@pytest.mark.parametrize("packages", [{}, {"": {"dependencies": {"missing": "1"}}}])
def test_production_closure_rejects_missing_required_roots_or_edges(
    packages: dict[str, object],
) -> None:
    """Missing lock facts produce explicit failures instead of silently reducing the inventory."""
    lock = FrontendLock.model_validate({"lockfileVersion": 3, "packages": packages})
    with pytest.raises(ValidationError, match="missing"):
        production_closure(lock)


def test_optional_peer_metadata_cannot_weaken_a_required_direct_dependency() -> None:
    """A missing direct dependency stays required even when also named as an optional peer."""
    lock = FrontendLock.model_validate(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {
                    "dependencies": {"required": "1"},
                    "peerDependencies": {"required": "1"},
                    "peerDependenciesMeta": {"required": {"optional": True}},
                }
            },
        }
    )
    with pytest.raises(ValidationError, match="missing required runtime dependency"):
        production_closure(lock)


def write_inventory(root: Path, packages: tuple[str, ...] = ()) -> Path:
    """Write measured package evidence bound to generated source and lock bytes."""
    output = root / "datakeel" / "web_dist"
    output.mkdir(parents=True, exist_ok=True)
    path = output / ".runtime-dependencies.json"
    inventory = BundleInventory(
        schema_version=1, source_hash=source_hash(root / "web"), packages=packages
    )
    path.write_text(inventory.model_dump_json())
    return path


def write_frontend(tmp_path: Path) -> Path:
    """Create a small generated npm tree with a forbidden transitive dependency license."""
    web = tmp_path / "web"
    web.mkdir()
    (web / "src").mkdir()
    (web / "src/main.js").write_text("import 'runtime';\n")
    packages = {
        "": FrontendPackage(name="application", dependencies={"runtime": "1"}),
        "node_modules/runtime": FrontendPackage(
            name="runtime", version="1", license="MIT", dependencies={"leaf": "1"}
        ),
        "node_modules/leaf": FrontendPackage(name="leaf", version="1", license="GPL-3.0"),
    }
    lock = FrontendLock(lockfileVersion=3, packages=packages)
    (web / "package-lock.json").write_text(lock.model_dump_json(by_alias=True))
    (web / "package.json").write_text(packages[""].model_dump_json(by_alias=True))
    for location, package in packages.items():
        if location:
            directory = web / location
            directory.mkdir(parents=True)
            (directory / "package.json").write_text(package.model_dump_json(by_alias=True))
    write_inventory(tmp_path, ("node_modules/leaf", "node_modules/runtime"))
    return web


def test_frontend_inventory_retains_actual_transitive_license(tmp_path: Path) -> None:
    """The report includes a transitive dependency even when its license is forbidden."""
    write_frontend(tmp_path)
    result = frontend_packages(tmp_path)
    assert [(item.name, item.version, item.license) for item in result] == [
        ("leaf", "1", "GPL-3.0"),
        ("runtime", "1", "MIT"),
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "2"),
        ("name", "different-package"),
        ("license", "GPL-3.0"),
        ("license", None),
        ("dependencies", {"unlocked-copyleft-child": "1"}),
        ("optionalDependencies", {"unlocked-copyleft-child": "1"}),
        ("peerDependencies", {"unlocked-copyleft-child": "1"}),
        ("peerDependenciesMeta", {"leaf": {"optional": True}}),
    ],
)
def test_frontend_inventory_rejects_installed_version_or_license_drift(
    tmp_path: Path, field: str, value: JsonValue
) -> None:
    """Changing installed metadata fails against the lock before any policy exemption applies."""
    web = write_frontend(tmp_path)
    path = web / "node_modules/runtime/package.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValidationError, match="metadata differs"):
        frontend_packages(tmp_path)


def test_frontend_inventory_rejects_missing_installation(tmp_path: Path) -> None:
    """An incomplete npm installation cannot silently lose a production package."""
    web = write_frontend(tmp_path)
    (web / "node_modules/leaf/package.json").unlink()
    with pytest.raises(ValidationError, match="not installed"):
        frontend_packages(tmp_path)


@pytest.mark.parametrize(
    "declaration",
    [
        '{"dependencies": {"replacement": "1"}}',
        '{"dependencies": {"runtime": "2"}}',
        '{"dependencies": {"runtime": "1"}, "peerDependencies": {"peer": "1"}}',
        '{"dependencies": {"runtime": "1"}, "optionalDependencies": {"optional": "1"}}',
    ],
)
def test_frontend_inventory_rejects_stale_root_dependencies(
    tmp_path: Path, declaration: str
) -> None:
    """Changing production roots requires a matching lock update."""
    web = write_frontend(tmp_path)
    (web / "package.json").write_text(declaration)
    with pytest.raises(ValidationError, match="runtime dependencies differ"):
        frontend_packages(tmp_path)


def test_bundled_dev_dependency_with_gpl_is_included_and_rejected(tmp_path: Path) -> None:
    """Actual build evidence brings dev-only packages into the audit without their build tools."""
    web = write_frontend(tmp_path)
    path = web / "package-lock.json"
    lock = json.loads(path.read_text())
    lock["packages"][""]["devDependencies"] = {"bundled-dev": "1"}
    lock["packages"]["node_modules/bundled-dev"] = {
        "name": "bundled-dev",
        "version": "1",
        "license": "GPL-3.0",
        "dev": True,
        "dependencies": {"unbundled-build-tool": "1"},
    }
    path.write_text(json.dumps(lock))
    directory = web / "node_modules/bundled-dev"
    directory.mkdir()
    (directory / "package.json").write_text(
        json.dumps(lock["packages"]["node_modules/bundled-dev"])
    )
    write_inventory(tmp_path, ("node_modules/bundled-dev", "node_modules/runtime"))
    result = frontend_packages(tmp_path)
    bundled = next(item for item in result if item.name == "bundled-dev")
    assert license_findings(bundled)[0].reason.endswith("GPL-3.0")
    assert not any(item.name == "unbundled-build-tool" for item in result)


def test_optional_production_dependency_absent_on_this_platform_is_not_audited(
    tmp_path: Path,
) -> None:
    """Uninstalled optional platform variants do not count as shipped runtime packages."""
    web = write_frontend(tmp_path)
    path = web / "package-lock.json"
    lock = json.loads(path.read_text())
    lock["packages"][""]["optionalDependencies"] = {"platform-variant": "1"}
    lock["packages"]["node_modules/platform-variant"] = {"version": "1", "license": "MIT"}
    path.write_text(json.dumps(lock))
    manifest_path = web / "package.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["optionalDependencies"] = {"platform-variant": "1"}
    manifest_path.write_text(json.dumps(manifest))
    write_inventory(tmp_path)
    assert [item.name for item in frontend_packages(tmp_path)] == ["leaf", "runtime"]


def test_unknown_measured_bundle_package_fails_closed(tmp_path: Path) -> None:
    """A package measured in the bundle must have locked metadata before it can be accepted."""
    write_frontend(tmp_path)
    write_inventory(tmp_path, ("node_modules/unlocked-package",))
    with pytest.raises(ValidationError, match="absent from the lock"):
        frontend_packages(tmp_path)
