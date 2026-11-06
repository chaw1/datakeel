# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Benchmark command isolation, persistence, and truthful threshold output."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from datakeel.cli import evidence_benchmark, evidence_evaluation
from datakeel.cli.evidence_benchmark import run_benchmark
from datakeel.core.errors import ExecutionError
from datakeel.core.evidence_eval import EvidenceEvalReport
from datakeel.core.models import new_id
from datakeel.harness.evidence_questions import load_evidence_questions
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions
from datakeel.storage.database import Database
from datakeel.storage.evidence_evaluations import list_evidence_evaluations
from tests.cli.conftest import Invoke


@pytest.fixture
def measured_report(db: Database, tmp_path: Path) -> EvidenceEvalReport:
    """Produce a genuine report whose configured recall-gain target cannot be met."""
    suite, _ = load_evidence_questions()
    payload = suite.model_dump(mode="json")
    payload["thresholds"]["recall_gain"] = 1
    contract = tmp_path / "questions.yaml"
    contract.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return run_benchmark(db, tmp_path / "samples", contract, samples=100)


def test_eval_evidence_when_threshold_false_prints_and_persists_without_nonzero_exit(
    db: Database,
    invoke: Invoke,
    measured_report: EvidenceEvalReport,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Metric shortfalls are data, while the independent parent persists every typed result."""
    assert not measured_report.threshold_met
    monkeypatch.setattr(
        evidence_evaluation,
        "isolated_evidence_evaluation",
        lambda _questions, **_options: measured_report.model_copy(update={"id": new_id()}),
    )
    invoke("eval-evidence", "--json")
    report = json.loads(capsys.readouterr().out)
    assert report["provider"] == "evidence"
    assert report["threshold_met"] is False
    assert len(report["questions"]) == 15
    assert "tokens" not in report
    assert "total_cost_usd" not in report
    assert list_evidence_evaluations(db)[0].id == report["id"]
    invoke("eval-evidence")
    assert "threshold_met=False" in capsys.readouterr().out
    assert len(list_evidence_evaluations(db)) == 2


def test_isolated_benchmark_when_user_has_remote_settings_does_not_inherit_them(
    measured_report: EvidenceEvalReport, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only local home/database/PATH reach the subprocess, including all worker threads."""
    monkeypatch.setenv("DATAKEEL_S3_BUCKET", "must-not-be-used")
    monkeypatch.setenv("DATAKEEL_OPENAI_API_KEY", "synthetic-disallowed-config")

    def child(command: list[str], **options: object) -> subprocess.CompletedProcess[str]:
        environment = options["env"]
        assert isinstance(environment, dict)
        assert set(environment) == {"PATH", "DATAKEEL_HOME", "DATAKEEL_DATABASE_URL"}
        assert str(environment["DATAKEEL_DATABASE_URL"]).startswith("sqlite:///")
        assert command[1:3] == ["-m", "datakeel.cli.evidence_benchmark"]
        Path(command[command.index("--output") + 1]).write_text(measured_report.model_dump_json())
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(evidence_evaluation.subprocess, "run", child)
    assert (
        evidence_evaluation.isolated_evidence_evaluation(tmp_path / "contract.yaml")
        == measured_report
    )


def test_isolated_benchmark_when_child_fails_does_not_publish_a_partial_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Execution errors remain failures even though valid metric shortfalls do not."""
    monkeypatch.setattr(
        evidence_evaluation.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 1, "", "synthetic extraction failure"
        ),
    )
    with pytest.raises(ExecutionError, match="synthetic extraction failure"):
        evidence_evaluation.isolated_evidence_evaluation()


def test_benchmark_main_writes_typed_report_and_disposes_database(
    db: Database,
    measured_report: EvidenceEvalReport,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The child entrypoint forwards the contract and releases its engine after writing JSON."""
    output = tmp_path / "report.json"
    questions = tmp_path / "questions.yaml"
    disposed: list[bool] = []
    monkeypatch.setattr(
        sys, "argv", ["benchmark", "--output", str(output), "--questions", str(questions)]
    )
    monkeypatch.setattr(evidence_benchmark, "Database", lambda: db)
    monkeypatch.setattr(db.engine, "dispose", lambda: disposed.append(True))

    def evaluate(
        database: Database, directory: Path, contract: Path | None, **options: object
    ) -> EvidenceEvalReport:
        assert database is db
        assert directory == evidence_benchmark.data_dir() / "samples"
        assert contract == questions
        assert options == {"mode": None}
        return measured_report

    monkeypatch.setattr(evidence_benchmark, "run_benchmark", evaluate)
    evidence_benchmark.main()
    assert EvidenceEvalReport.model_validate_json(output.read_text()) == measured_report
    assert disposed == [True]


def test_benchmark_main_on_extraction_failure_disposes_without_writing_report(
    db: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed child leaves no misleading artifact and still releases database resources."""
    output = tmp_path / "report.json"
    disposed: list[bool] = []
    monkeypatch.setattr(sys, "argv", ["benchmark", "--output", str(output)])
    monkeypatch.setattr(evidence_benchmark, "Database", lambda: db)
    monkeypatch.setattr(db.engine, "dispose", lambda: disposed.append(True))

    def fail(*_args: object, **_options: object) -> EvidenceEvalReport:
        message = "Synthetic failed extraction"
        raise ExecutionError(message)

    monkeypatch.setattr(evidence_benchmark, "run_benchmark", fail)
    with pytest.raises(ExecutionError, match="Synthetic failed extraction"):
        evidence_benchmark.main()
    assert not output.exists()
    assert disposed == [True]


def test_benchmark_main_on_initialization_failure_disposes_without_writing_report(
    db: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Schema failures propagate before extraction and still release the child engine."""
    output = tmp_path / "report.json"
    disposed: list[bool] = []
    monkeypatch.setattr(sys, "argv", ["benchmark", "--output", str(output)])
    monkeypatch.setattr(evidence_benchmark, "Database", lambda: db)
    monkeypatch.setattr(db.engine, "dispose", lambda: disposed.append(True))

    def fail(*_args: object, **_options: object) -> None:
        message = "Synthetic initialization failure"
        raise ExecutionError(message)

    if db.sqlite:
        monkeypatch.setattr(evidence_benchmark, "initialize", fail)
    else:
        monkeypatch.setattr(db, "migrate", fail)

    def unexpected(*_args: object, **_options: object) -> EvidenceEvalReport:
        pytest.fail("Extraction must not run after initialization fails")

    monkeypatch.setattr(evidence_benchmark, "run_benchmark", unexpected)
    with pytest.raises(ExecutionError, match="Synthetic initialization failure"):
        evidence_benchmark.main()
    assert not output.exists()
    assert disposed == [True]


@pytest.mark.parametrize("failure", ["migration", "extraction"])
def test_benchmark_postgres_initialization_and_failure_cleanup_without_sockets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    """The PG branch passes complete W3 contracts and disposes on either error path."""
    database = Database("postgresql+pg8000://localhost/unused")
    output = tmp_path / "report.json"
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    disposed: list[bool] = []
    monkeypatch.setattr(sys, "argv", ["benchmark", "--output", str(output)])
    monkeypatch.setattr(evidence_benchmark, "Database", lambda: database)
    monkeypatch.setattr(database.engine, "dispose", lambda: disposed.append(True))

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("PG initialization must not use SQLite initialization or open sockets")

    def migrate(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        if failure == "migration":
            raise ExecutionError(failure)

    def extract(*_args: object, **_kwargs: object) -> EvidenceEvalReport:
        raise ExecutionError(failure)

    monkeypatch.setattr(evidence_benchmark, "initialize", forbidden)
    monkeypatch.setattr(database.engine, "connect", forbidden)
    monkeypatch.setattr(database, "migrate", migrate)
    monkeypatch.setattr(evidence_benchmark, "run_benchmark", extract)
    with pytest.raises(ExecutionError, match=failure):
        evidence_benchmark.main()
    assert calls == [((schema_contributions(),), {"canonical": canonical_schema()})]
    assert disposed == [True]
    assert not output.exists()


def test_benchmark_when_worker_does_not_finish_rejects_partial_observations(
    db: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The benchmark refuses to evaluate a task whose worker returns a failed outcome."""
    monkeypatch.setattr(evidence_benchmark, "execute", lambda *_args: False)
    with pytest.raises(ExecutionError, match="did not complete"):
        run_benchmark(db, tmp_path / "samples", samples=100)


def test_benchmark_exact_recovers_all_generated_pairs(db: Database, tmp_path: Path) -> None:
    """Run exact mode through the real production DAG, including cross-prefix neighbors."""
    report = run_benchmark(db, tmp_path / "samples", samples=100, mode="exact")
    assert report.near_duplicate_mode == "exact"
    assert report.near_duplicate_pairs.recall == 1.0
    assert report.val_to_train_pairs.recall == 1.0


def test_isolated_benchmark_forwards_exact_mode(
    measured_report: EvidenceEvalReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The parent's explicit mode must reach the isolated comparison process."""

    def child(command: list[str], **_options: object) -> subprocess.CompletedProcess[str]:
        assert command[command.index("--mode") + 1] == "exact"
        Path(command[command.index("--output") + 1]).write_text(measured_report.model_dump_json())
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(evidence_evaluation.subprocess, "run", child)
    assert evidence_evaluation.isolated_evidence_evaluation(mode="exact") == measured_report
