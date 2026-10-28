# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute only approved custom versions and retain every sandbox attempt's audit."""

import hashlib
import json
from pathlib import Path

from datakeel.core.custom_operators import CustomOperatorRun
from datakeel.core.custom_sandbox import SandboxInput, SandboxLimits, SandboxRequest, SandboxResult
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import FileItem, JsonDocument, new_id, utcnow
from datakeel.evidence.execution import EvidenceExecution
from datakeel.operators import OperatorResult
from datakeel.operators.custom_sandbox import run_sandbox
from datakeel.pipeline.models import Node
from datakeel.storage.custom_store import approved_in_session, record_custom_run
from datakeel.storage.custom_validation import validate_custom_pipeline
from datakeel.storage.database import Database
from datakeel.storage.task_queue import Lease


def _inputs(files: list[FileItem], limits: SandboxLimits) -> tuple[SandboxInput, ...]:
    remaining = limits.max_input_bytes
    inputs: list[SandboxInput] = []
    for file in files:
        with Path(file.path).open("rb") as source:
            content = source.read(remaining + 1)
        remaining -= len(content)
        if remaining < 0:
            msg = "Custom operator inputs exceed the sandbox input byte limit"
            raise ValidationError(msg)
        inputs.append(
            SandboxInput(
                name=file.filename,
                content=content,
                metadata=JsonDocument.model_validate(file.metadata).root,
            )
        )
    return tuple(inputs)


def _outputs(result: SandboxResult, directory: Path, modality: str) -> list[FileItem]:
    directory.mkdir(parents=True, exist_ok=True)
    files: list[FileItem] = []
    for output in result.outputs:
        identifier = new_id()
        target = directory / identifier
        target.write_bytes(output.content)
        files.append(
            FileItem(
                id=identifier,
                path=str(target.resolve()),
                filename=output.name,
                sha256=hashlib.sha256(output.content).hexdigest(),
                size=len(output.content),
                modality=modality,
                metadata=output.metadata,
            )
        )
    return files


class CustomExecution:
    """Dispatch custom nodes through the sandbox while preserving existing evidence execution."""

    def __init__(self, db: Database, lease: Lease, evidence: EvidenceExecution) -> None:
        """Bind audit identities to one fenced worker attempt."""
        self.db, self.lease, self.evidence = db, lease, evidence

    def execute_node(self, node: Node, files: list[FileItem], directory: Path) -> OperatorResult:
        """Load approved content, execute it in isolation, and publish only validated bytes."""
        if node.operator is None or not node.operator.startswith("custom."):
            return self.evidence.execute_node(node, files, directory)
        with self.db.session() as session:
            version = approved_in_session(session, node.operator)
            validate_custom_pipeline(session, self.lease.pipeline)
        if version.modality != "any" and any(file.modality != version.modality for file in files):
            msg = "Custom operator input modality does not match its approved declaration"
            raise ValidationError(msg)
        params = JsonDocument.model_validate(node.params)
        started = utcnow()
        request = SandboxRequest(
            code=version.code,
            code_hash=version.code_hash,
            inputs=_inputs(files, SandboxLimits()),
            params=params.root,
            parameter_schema=version.parameter_schema.root,
            metadata_schema=version.metadata_schema.root,
        )
        result = run_sandbox(request)
        record = CustomOperatorRun(
            id=new_id(),
            operator=version.id,
            code_hash=version.code_hash,
            image_digest=result.image_digest,
            backend=result.backend,
            params_digest=hashlib.sha256(
                json.dumps(
                    params.root,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            ).hexdigest(),
            task_id=self.lease.task_id,
            shard_id=self.lease.shard_id,
            node_id=node.id,
            attempt_id=self.lease.owner,
            created_at=started,
            completed_at=utcnow(),
            success=result.success,
            exit_reason=result.exit_reason,
            resources=JsonDocument(result.resources.model_dump(mode="json")),
            output_count=len(result.outputs),
        )
        record_custom_run(self.db, record, self.lease.dataset_id)
        if not result.success:
            msg = f"Custom operator sandbox failed: {result.exit_reason}"
            if result.exit_reason == "runtime_error" and result.stderr:
                msg += f": {result.stderr}"
            raise ExecutionError(msg)
        modality = version.modality
        if modality == "any":
            modes = {file.modality for file in files}
            modality = modes.pop() if len(modes) == 1 else "unknown"
        return OperatorResult(
            files=_outputs(result, directory, modality),
            quality={"custom_operator": record.model_dump(mode="json")},
        )
