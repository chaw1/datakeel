# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Make a started cloud run's model calls outside every transaction and save each batch alone.

Up to four images are sent at a time, each admitted only if the measured spend plus its estimate
stays inside the action budget. No database transaction is open while the provider answers. Each
batch's drafts, failures and spend are then written in one short transaction that re-reads and
locks just those tasks: a task that was drafted or claimed meanwhile is left untouched. If the run
was taken over as abandoned, nothing more is written and no further image is sent.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.core.errors import DatakeelError
from datakeel.core.models import utcnow
from datakeel.core.prelabel_models import PrelabelCall, PrelabelDrop, PrelabelStop, TaskTier
from datakeel.core.production_catalog_models import (
    PredictionFailure,
    PrelabelRun,
    ProductionModel,
)
from datakeel.core.production_models import Project
from datakeel.prelabel import image_estimate, open_client
from datakeel.storage.action_locks import lock_row_writes
from datakeel.storage.database import Database
from datakeel.storage.production_catalog import require_model
from datakeel.storage.production_cloud_labeling import (
    FAILURE_MESSAGES,
    CloudRequest,
    ImageOutcome,
    label_image,
)
from datakeel.storage.production_cloud_prelabel import (
    EDITABLE_STATES,
    CloudTargets,
    cloud_request_for,
    cloud_targets,
)
from datakeel.storage.production_prelabel_runs import locked_run, prediction_samples, store_run
from datakeel.storage.production_prelabel_writes import prelabeled_task_ids, write_model_draft
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_task_images import sample_keys
from datakeel.storage.production_tasks import require_mutable_project

PARALLEL_IMAGES = 4
CHANGED_MESSAGE = "The task was drafted or edited while the model ran; it was left as it is"


class Ledger:
    """Accumulate per-image results for one run."""

    def __init__(self) -> None:
        """Start with nothing spent, sent or written."""
        self.spent = Decimal(0)
        self.calls: list[PrelabelCall] = []
        self.drops: list[PrelabelDrop] = []
        self.failures: list[PredictionFailure] = []
        self.revision_ids: list[str] = []
        self.confidences: list[float] = []
        self.tiers: list[TaskTier] = []
        self.sent = 0
        self.taken_over = False

    def next_image_cost(self) -> Decimal | None:
        """Use this run's measured average per sent image once one has been sent."""
        return self.spent / self.sent if self.sent else None

    def snapshot(self, record: PrelabelRun, stopped: PrelabelStop | None) -> PrelabelRun:
        """Return the run record as of now: outputs, failures, calls, tokens and spend."""
        now = utcnow()
        return record.model_copy(
            update={
                "revision_ids": tuple(self.revision_ids),
                "confidences": tuple(self.confidences),
                "failures": tuple(self.failures),
                "cost": float(self.spent),
                "input_tokens": sum(call.input_tokens for call in self.calls),
                "output_tokens": sum(call.output_tokens for call in self.calls),
                "calls": tuple(self.calls),
                "dropped": tuple(self.drops),
                "stopped": stopped,
                "tiers": tuple(self.tiers),
                "completed_images": len(self.revision_ids),
                "failed_images": len(self.failures),
                "elapsed_seconds": (now - record.created_at).total_seconds(),
                "updated_at": now,
            }
        )


class _Target(NamedTuple):
    id: str
    sample_id: str
    head: str | None


class _Run(NamedTuple):
    db: Database
    params: RunPrelabelParams
    record: PrelabelRun
    project: Project
    model: ProductionModel
    request: CloudRequest
    targets: CloudTargets
    pending: tuple[_Target, ...]
    keys: dict[str, str]
    filenames: dict[str, str]


def _load(db: Database, params: RunPrelabelParams, run_id: str) -> _Run:
    """Read everything the calls need in one short read, then let the transaction go."""
    with db.session() as session:
        _, record = locked_run(session, run_id)
        project = require_mutable_project(session, record.project_id)
        model = require_model(session, record.model_id)
        request = cloud_request_for(session, project, model)
        targets = cloud_targets(session, project, model, record.package_id, lock=False)
        keys = sample_keys(session, project)
        filenames = {sample.id: sample.filename for sample in prediction_samples(session, project)}
        pending = tuple(
            _Target(task.id, task.sample_id, task.latest_revision_id) for task in targets.tasks
        )
        session.rollback()
    return _Run(
        db,
        params,
        record,
        project,
        model,
        request,
        targets._replace(tasks=[]),
        pending,
        keys,
        filenames,
    )


def _fail(
    run: _Run, ledger: Ledger, task: ProductionTaskRow | _Target, code: str, message: str
) -> None:
    ledger.failures.append(
        PredictionFailure(
            filename=run.filenames.get(task.sample_id, task.sample_id),
            sample_id=task.sample_id,
            code=code,
            message=message,
        )
    )


def _account(run: _Run, ledger: Ledger, outcome: ImageOutcome) -> None:
    """Every sent image is paid for, whatever then happens to its result."""
    if outcome.calls:
        ledger.spent += outcome.cost + Decimal(str(run.model.unit_price))
        ledger.sent += 1
    ledger.calls.extend(outcome.calls)
    ledger.drops.extend(outcome.drops)


def _record(
    session: Session,
    run: _Run,
    ledger: Ledger,
    task: ProductionTaskRow,
    outcome: ImageOutcome,
    done: set[str],
) -> None:
    _account(run, ledger, outcome)
    if outcome.prediction is None:
        code = outcome.failure or "invalid_response"
        _fail(run, ledger, task, code, FAILURE_MESSAGES.get(code, "The provider returned an error"))
        return
    if task.id in done or task.state not in EDITABLE_STATES:
        _fail(run, ledger, task, "task_changed", CHANGED_MESSAGE)
        return
    record = run.record
    if record.thresholds is None or record.actor is None:
        message = "A started run records its thresholds and actor"
        raise ValueError(message)
    try:
        with session.begin_nested():
            revision_id, tier = write_model_draft(
                session,
                run.project,
                task,
                outcome.prediction,
                run.model,
                record.actor,
                request_id=run.params.request_id,
                thresholds=record.thresholds,
            )
    except DatakeelError as exc:
        _fail(run, ledger, task, "revision_rejected", str(exc))
        return
    ledger.revision_ids.append(revision_id)
    ledger.confidences.append(outcome.prediction.confidence)
    ledger.tiers.append(tier)


def _write_batch(
    run: _Run, ledger: Ledger, batch: list[_Target], outcomes: list[ImageOutcome]
) -> None:
    """Write one batch in its own short transaction, after re-reading and locking its tasks."""
    with run.db.session() as session:
        lock_row_writes(run.db, session)
        row, current = locked_run(session, run.record.id)
        if current.status != "running":
            ledger.taken_over = True
            session.rollback()
            return
        identifiers = sorted(task.id for task in batch)
        tasks = {
            task.id: task
            for task in session.scalars(
                select(ProductionTaskRow)
                .where(ProductionTaskRow.id.in_(identifiers))
                .order_by(ProductionTaskRow.id)
                .with_for_update()
            )
        }
        # A person who saved meanwhile keeps their head: a draft never lands on newer work.
        done = prelabeled_task_ids(session, identifiers, run.model) | {
            target.id
            for target in batch
            if target.id in tasks and tasks[target.id].latest_revision_id != target.head
        }
        for target, outcome in zip(batch, outcomes, strict=True):
            task = tasks.get(target.id)
            if task is None:
                _account(run, ledger, outcome)
                _fail(run, ledger, target, "task_changed", CHANGED_MESSAGE)
                continue
            _record(session, run, ledger, task, outcome, done)
        store_run(row, ledger.snapshot(current, None))
        session.commit()


def _next_cost(run: _Run, ledger: Ledger, task: _Target) -> Decimal:
    size = run.targets.sizes.get(task.sample_id, (None, None))
    return ledger.next_image_cost() or image_estimate(
        run.request.config,
        run.model.unit_price,
        size,
        run.targets.output_tokens,
        run.targets.prompt_tokens,
    )


def _stop(run: _Run, ledger: Ledger, position: int) -> PrelabelStop:
    tasks = run.pending
    return PrelabelStop(
        before_sample_id=tasks[position].sample_id,
        completed_images=position,
        remaining_images=len(tasks) - position,
        spent=float(ledger.spent),
        budget=run.params.budget,
        next_image_estimate=float(_next_cost(run, ledger, tasks[position])),
    )


def label_remaining(
    db: Database, params: RunPrelabelParams, run_id: str
) -> tuple[Ledger, PrelabelStop | None]:
    """Send up to four images at a time, admitting each only if the budget still covers it."""
    run = _load(db, params, run_id)
    ledger = Ledger()
    budget = Decimal(str(params.budget))
    tasks = run.pending
    position = 0
    with open_client() as client, ThreadPoolExecutor(PARALLEL_IMAGES) as pool:
        while position < len(tasks) and not ledger.taken_over:
            batch: list[_Target] = []
            planned = ledger.spent
            for task in tasks[position : position + PARALLEL_IMAGES]:
                next_cost = _next_cost(run, ledger, task)
                if planned + next_cost > budget:
                    break
                planned += next_cost
                batch.append(task)
            if not batch:
                return ledger, _stop(run, ledger, position)

            def send(task: _Target) -> ImageOutcome:
                return label_image(
                    run.request, task.sample_id, run.keys.get(task.sample_id), client
                )

            outcomes = list(pool.map(send, batch))
            _write_batch(run, ledger, batch, outcomes)
            position += len(batch)
    return ledger, None


def finish_run(
    session: Session, run_id: str, ledger: Ledger | None, stopped: PrelabelStop | None
) -> PrelabelRun:
    """Close a run as completed, or as failed when its calls ended in an unexpected error."""
    row, current = locked_run(session, run_id)
    if current.status != "running":
        return current
    final = (
        ledger.snapshot(current, stopped)
        if ledger is not None
        else current.model_copy(update={"updated_at": utcnow()})
    )
    final = final.model_copy(update={"status": "completed" if ledger is not None else "failed"})
    store_run(row, final)
    return final
