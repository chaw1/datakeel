# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""License policy rejects unknown metadata, forbidden terms, and broadened exceptions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts import license_audit
from scripts.license_models import LicensePackage, LicenseReport, MplEvidence

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
        mpl=MplEvidence(
            source_url="https://example.org/generated/source",
            integrity="generated locked upstream SHA-256 evidence",
            notices=("LICENSE SHA-256 generated fixture",),
        ),
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
        "BUSL-1.1",
        "BSL-1.0",
        "PostgreSQL-like",
        "PostgreSQL-1.0",
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


@pytest.mark.parametrize("ecosystem", ["python", "frontend", "sandbox-python"])
@pytest.mark.parametrize(
    "expression", ["PostgreSQL", "PostgreSQL AND MIT", "MPL-2.0", "MPL-2.0 AND (Apache-2.0 OR MIT)"]
)
def test_general_policy_applies_to_all_runtime_ecosystems(ecosystem: str, expression: str) -> None:
    """General allowances include sandbox Python while MPL retains mandatory evidence."""
    generated = package(expression).model_copy(update={"ecosystem": ecosystem})
    assert license_audit.license_findings(generated) == ()


@pytest.mark.parametrize("ecosystem", ["python", "frontend", "sandbox-python"])
@pytest.mark.parametrize(
    "term", ["GPL-3.0-only", "LGPL-3.0-only", "AGPL-3.0-only", "BUSL-1.1", "SSPL-1.0", "UNKNOWN"]
)
def test_mpl_compound_cannot_hide_forbidden_terms(ecosystem: str, term: str) -> None:
    """An allowed MPL term cannot authorize another forbidden term in either operator branch."""
    for operator in ("AND", "OR"):
        generated = package(f"MPL-2.0 {operator} {term}").model_copy(
            update={"ecosystem": ecosystem}
        )
        assert license_audit.license_findings(generated)


@pytest.mark.parametrize("name", ["certifi", "orjson", "generated-package"])
@pytest.mark.parametrize("ecosystem", ["python", "frontend", "sandbox-python"])
def test_mpl_requires_evidence_even_for_previous_package_exceptions(
    name: str, ecosystem: str
) -> None:
    """Neither former certifi nor exact orjson exceptions waive the general evidence rule."""
    expression = license_audit.PACKAGE_EXCEPTIONS["orjson"] if name == "orjson" else "MPL-2.0"
    generated = package(expression, name).model_copy(update={"ecosystem": ecosystem, "mpl": None})
    assert license_audit.license_findings(generated)


@pytest.mark.parametrize("ecosystem", ["python", "frontend", "sandbox-python", "rust"])
def test_regex_exception_stays_exact_and_python_only(ecosystem: str) -> None:
    """CNRI remains restricted to the exact reviewed Python regex expression."""
    expression = license_audit.PACKAGE_EXCEPTIONS["regex"]
    approved = package(expression, "regex").model_copy(update={"ecosystem": ecosystem})
    assert bool(license_audit.license_findings(approved)) == (ecosystem != "python")
    for changed in (
        approved.model_copy(update={"name": "different-package"}),
        approved.model_copy(update={"license": expression + " AND GPL-3.0-only"}),
        approved.model_copy(update={"license": "CNRI-Python"}),
    ):
        assert license_audit.license_findings(changed)


@pytest.mark.parametrize("name", ["orjson", "regex"])
def test_exact_python_exceptions_cannot_add_terms(name: str) -> None:
    """An exact package exception cannot excuse any added non-allowlisted term."""
    expression = license_audit.PACKAGE_EXCEPTIONS[name]
    assert license_audit.license_findings(package(expression, name)) == ()
    for term in ("GPL-3.0-only", "CNRI-Python", "LicenseRef-Unknown"):
        assert license_audit.license_findings(package(expression + " AND " + term, name))


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


def test_audit_combines_all_dependency_closures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runtime reporting retains allowed and rejected packages from all ecosystems."""
    python = package("MIT")
    frontend = package("GPL-3.0").model_copy(update={"ecosystem": "frontend"})

    rust = package("MIT OR Apache-2.0").model_copy(update={"ecosystem": "rust"})

    def python_packages(_root: Path) -> tuple[LicensePackage, ...]:
        return (python,)

    def frontend_packages(_root: Path) -> tuple[LicensePackage, ...]:
        return (frontend,)

    def rust_packages(_root: Path) -> tuple[LicensePackage, ...]:
        return (rust,)

    monkeypatch.setattr(license_audit, "rust_packages", rust_packages)
    monkeypatch.setattr(license_audit, "python_packages", python_packages)
    monkeypatch.setattr(license_audit, "frontend_packages", frontend_packages)
    report = license_audit.audit(tmp_path)
    assert report.packages == (python, frontend, rust)
    assert len(report.findings) == 1
    assert report.findings[0].ecosystem == "frontend"


@pytest.mark.parametrize("license_id", sorted(license_audit.RUST_ALLOWED_LICENSES))
def test_rust_license_policy_accepts_only_declared_permissive_terms(license_id: str) -> None:
    """Rust's approved identifiers are independent of the main runtime allowlist."""
    rust = package(license_id).model_copy(update={"ecosystem": "rust"})
    assert license_audit.license_findings(rust) == ()


@pytest.mark.parametrize(
    "license_id",
    ["PostgreSQL", "MPL-2.0", "MIT-0", "ISC", "Zlib", "UNKNOWN", "", "MIT OR GPL-3.0-only"],
)
def test_rust_license_policy_rejects_unknown_or_broadened_terms(license_id: str) -> None:
    """Neither main-package allowances nor package exceptions admit Rust dependencies."""
    rust = package(license_id, "certifi").model_copy(update={"ecosystem": "rust"})
    assert license_audit.license_findings(rust)


def test_rust_apache_compiled_artifact_exception_is_exact_and_ecosystem_bound() -> None:
    """The permissive Apache artifact exception cannot broaden other terms or ecosystems."""
    rust = package("Apache-2.0 WITH LLVM-exception").model_copy(update={"ecosystem": "rust"})
    assert license_audit.license_findings(rust) == ()
    for changed in (
        rust.model_copy(update={"ecosystem": "python"}),
        rust.model_copy(update={"ecosystem": "frontend"}),
        rust.model_copy(update={"license": "Apache-2.0 WITH LLVM-exception AND GPL-3.0-only"}),
        rust.model_copy(update={"license": "MIT WITH LLVM-exception"}),
    ):
        assert license_audit.license_findings(changed)
