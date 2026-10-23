# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""License policy rejects unknown metadata, forbidden terms, and broadened exceptions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts import license_audit
from scripts.license_models import LicensePackage, LicenseReport

if TYPE_CHECKING:
    from pathlib import Path


def package(license_id: str, name: str = "generated-package") -> LicensePackage:
    """Create a generated distribution identity with explicitly declared license evidence."""
    return LicensePackage(
        ecosystem="python",
        name=name,
        version="1.0",
        license=license_id,
        evidence="generated METADATA",
    )


@pytest.mark.parametrize("license_id", sorted(license_audit.ALLOWED_LICENSES))
def test_exact_allowed_spdx_identifiers_pass(license_id: str) -> None:
    """Every explicitly allowed identifier passes without fuzzy name matching."""
    assert license_audit.license_findings(package(license_id)) == ()


@pytest.mark.parametrize("license_id", ["MIT-0", "CC0-1.0", "MIT-CMU"])
@pytest.mark.parametrize("ecosystem", ["python", "frontend"])
def test_new_permissive_licenses_apply_to_all_packages_and_ecosystems(
    license_id: str, ecosystem: str
) -> None:
    """The permissive additions are general policy, independent of existing dependency names."""
    generated = package(license_id).model_copy(update={"ecosystem": ecosystem})
    assert license_audit.license_findings(generated) == ()


@pytest.mark.parametrize(
    "license_id",
    [
        "GPL-3.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "LGPL-2.1-only",
        "LGPL-2.1-or-later",
        "LGPL-3.0-only",
        "LGPL-3.0-or-later",
        "SSPL-1.0",
        "MPL-2.0",
        "UNKNOWN",
        "",
        "LicenseRef-PrivateTerms",
        "MIT OR GPL-3.0-only",
        "MIT-0 OR AGPL-3.0-only",
        "CC0-1.0 AND LGPL-3.0-only",
        "MIT-CMU AND SSPL-1.0",
        "MIT AND LicenseRef-Unknown",
        "Apache-2.0 WITH LLVM-exception",
        "MIT AND",
        "MIT nonsense BSD-3-Clause",
    ],
)
def test_forbidden_or_unknown_license_expression_fails_closed(license_id: str) -> None:
    """Unknown, malformed, and disallowed SPDX terms cannot hide inside permissive text."""
    findings = license_audit.license_findings(package(license_id))
    assert len(findings) == 1
    assert findings[0].license == license_id
    assert findings[0].reason


def test_all_terms_in_valid_compound_expression_are_checked() -> None:
    """AND, OR, and parentheses are parsed as SPDX syntax rather than substring matches."""
    permitted = "MIT AND (BSD-3-Clause OR Apache-2.0) AND MIT-0 AND CC0-1.0 AND MIT-CMU"
    assert license_audit.license_findings(package(permitted)) == ()
    blocked = "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 AND LGPL-3.0-only"
    assert license_audit.license_findings(package(blocked))[0].reason.endswith("LGPL-3.0-only")


def test_certifi_exception_cannot_cover_other_packages_ecosystems_or_extra_terms() -> None:
    """The existing root-certificate exception permits only certifi's exact MPL expression."""
    approved = package("MPL-2.0", "certifi")
    assert license_audit.license_findings(approved) == ()
    for changed in (
        approved.model_copy(update={"name": "different-package"}),
        approved.model_copy(update={"ecosystem": "frontend"}),
        approved.model_copy(update={"license": "MPL-2.0 AND GPL-3.0-only"}),
    ):
        assert license_audit.license_findings(changed)


@pytest.mark.parametrize(
    ("license_id", "exit_code"),
    [
        ("MIT", 0),
        ("MIT-0", 0),
        ("CC0-1.0", 0),
        ("MIT-CMU", 0),
        ("GPL-3.0", 1),
        ("AGPL-3.0-only", 1),
        ("LGPL-3.0-only", 1),
        ("SSPL-1.0", 1),
        ("UNKNOWN", 1),
        ("", 1),
    ],
)
def test_cli_writes_reviewable_report_and_returns_policy_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, license_id: str, exit_code: int
) -> None:
    """A modified dependency license produces both a failed exit and concrete report evidence."""
    item = package(license_id)
    report = LicenseReport(
        python_target="generated target",
        packages=(item,),
        findings=license_audit.license_findings(item),
    )

    def fixed_report(_root: Path) -> LicenseReport:
        return report

    monkeypatch.setattr(license_audit, "audit", fixed_report)
    json_path = tmp_path / "audit.json"
    monkeypatch.setattr(
        "sys.argv", ["license_audit.py", "--root", str(tmp_path), "--json-report", str(json_path)]
    )
    with pytest.raises(SystemExit) as stopped:
        license_audit.main()
    assert stopped.value.code == exit_code
    saved = json.loads(json_path.read_text())
    assert len(saved["findings"]) == exit_code
    assert saved["packages"][0]["license"] == license_id
    notices = (tmp_path / "THIRD_PARTY_NOTICES.md").read_text()
    assert f"| python | generated-package | 1.0 | {license_id} |" in notices
    assert str(tmp_path) not in notices


def test_audit_combines_both_dependency_closures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runtime reporting retains allowed and rejected packages from both ecosystems."""
    python = package("MIT")
    frontend = package("GPL-3.0").model_copy(update={"ecosystem": "frontend"})

    def python_packages(_root: Path) -> tuple[LicensePackage, ...]:
        return (python,)

    def frontend_packages(_root: Path) -> tuple[LicensePackage, ...]:
        return (frontend,)

    monkeypatch.setattr(license_audit, "python_packages", python_packages)
    monkeypatch.setattr(license_audit, "frontend_packages", frontend_packages)
    report = license_audit.audit(tmp_path)
    assert report.packages == (python, frontend)
    assert len(report.findings) == 1
    assert report.findings[0].ecosystem == "frontend"
