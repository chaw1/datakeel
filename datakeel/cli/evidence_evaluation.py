# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolate benchmark execution from user queues, backends, credentials, and model providers."""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console

from datakeel.core.errors import ExecutionError
from datakeel.core.evidence_eval import EvidenceEvalReport
from datakeel.harness.resources import contract_path
from datakeel.storage.database import Database
from datakeel.storage.evidence_evaluations import save_evidence_evaluation


def isolated_evidence_evaluation(questions: Path | None = None) -> EvidenceEvalReport:
    """Launch a fresh local-only benchmark without inheriting any process configuration."""
    with TemporaryDirectory(prefix="datakeel-evidence-eval-") as temporary:
        directory = Path(temporary)
        output = directory / "report.json"
        command = [
            sys.executable,
            "-m",
            "datakeel.cli.evidence_benchmark",
            "--output",
            str(output),
            "--questions",
            str((questions or contract_path("evidence/questions.yaml")).resolve()),
        ]
        result = subprocess.run(  # noqa: S603  # Fixed module and argv; no shell or inherited settings.
            command,
            env={
                "PATH": os.defpath,
                "DATAKEEL_HOME": str(directory / "home"),
                "DATAKEEL_DATABASE_URL": f"sqlite:///{directory / 'benchmark.db'}",
            },
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        if result.returncode != 0:
            msg = f"Evidence benchmark failed: {result.stderr[-2000:]}"
            raise ExecutionError(msg)
        return EvidenceEvalReport.model_validate_json(output.read_bytes())


def evaluate_evidence(
    db: Database, questions: Path | None = None, *, json_output: bool = False
) -> None:
    """Persist complete measurements and display unmet thresholds without failing the command."""
    report = save_evidence_evaluation(db, isolated_evidence_evaluation(questions))
    console = Console()
    if json_output:
        console.print(
            report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True
        )
        return
    console.print(
        f"Evidence: {len(report.questions)} questions; {report.sample_count} fresh samples"
    )
    for result in report.questions:
        console.print(
            f"{result.id}: baseline P={result.baseline.precision:.4f} "
            f"R={result.baseline.recall:.4f}; "
            f"evidence P={result.with_evidence.precision:.4f} R={result.with_evidence.recall:.4f}",
            markup=False,
        )
    console.print(f"Macro baseline: {report.baseline_macro.model_dump_json()}")
    console.print(f"Macro with evidence: {report.with_evidence_macro.model_dump_json()}")
    console.print(f"Direct pairs: {report.near_duplicate_pairs.model_dump_json()}")
    console.print(f"Val-to-train pairs: {report.val_to_train_pairs.model_dump_json()}")
    console.print(f"Presence: {report.presence_counts.model_dump_json()}")
    console.print(f"Fresh extraction: {report.extraction.model_dump_json()}")
    console.print(f"threshold_met={report.threshold_met}; report={report.id}")
