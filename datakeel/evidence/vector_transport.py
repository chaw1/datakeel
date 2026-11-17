# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The sole vector transport: a local synthetic fake with durable predispatch fencing."""

import hashlib
import json
import struct
from http import HTTPStatus
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, ValidationError

from datakeel.core.models import BoundaryModel
from datakeel.core.vector_models import FrozenVectorNode, VectorError, VectorPermit
from datakeel.evidence.vector_payload import PreparedWire
from datakeel.storage.database import Database
from datakeel.storage.vector_authorization import authorize_vector
from datakeel.storage.vector_budget import dispatch_vector


class FakeUsage(BoundaryModel):
    """Require the invented fake total_tokens to be a nonnegative strict integer."""

    total_tokens: int = Field(ge=0, strict=True)


class FakeEmbedding(BoundaryModel):
    """Map each vector to the exact local request index."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object: Literal["embedding"]
    index: int = Field(ge=0, strict=True)
    embedding: tuple[Annotated[float, Field(allow_inf_nan=False)], ...]


class FakeResponse(BoundaryModel):
    """Accept only the frozen E1 response subset, without invented provider fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str = Field(min_length=1, max_length=200, pattern=r"^[a-zA-Z0-9_-]+$")
    object: Literal["list"]
    model: Literal["text-embedding-v4", "multimodal-embedding-v1"]
    data: tuple[FakeEmbedding, ...]
    usage: FakeUsage


class FakeReply(BoundaryModel):
    """Represent a local fake status and bytes, including refusal/redirect fixtures."""

    status: int = 200
    body: bytes


def verify_predispatch(
    db: Database, permit: VectorPermit, node: FrozenVectorNode, wire: PreparedWire
) -> None:
    """Reverify consumed approval, lease ownership and frozen wire hash before dispatch."""
    with db.session() as session:
        prepared = authorize_vector(session, permit)
        if node not in prepared.nodes or wire.frozen not in node.inputs:
            msg = "vector_transport_plan_mismatch"
            raise VectorError(msg)
    if hashlib.sha256(wire.body).hexdigest() != wire.frozen.body_hash:
        msg = "vector_final_payload_changed"
        raise VectorError(msg)


def commit_dispatch(
    db: Database, permit: VectorPermit, attempt_id: str, wire: PreparedWire
) -> None:
    """Transition the reserved attempt to SENDING before crossing a transport boundary."""
    dispatch_vector(db, permit, attempt_id, wire.frozen)


class VectorDispatchGate:
    """Bind predispatch verification and SENDING transition without exposing storage types."""

    def __init__(
        self,
        db: Database,
        permit: VectorPermit,
        node: FrozenVectorNode,
        wire: PreparedWire,
        attempt_id: str,
    ) -> None:
        """Capture the leased worker identity and reserved attempt for one transport call."""
        self._db = db
        self._permit = permit
        self._node = node
        self._wire = wire
        self._attempt_id = attempt_id

    def verify(self) -> None:
        """Reverify consumed approval, lease ownership and frozen wire hash before dispatch."""
        verify_predispatch(self._db, self._permit, self._node, self._wire)

    def commit(self) -> None:
        """Persist SENDING before any external socket or fake boundary is crossed."""
        commit_dispatch(self._db, self._permit, self._attempt_id, self._wire)


class FakeVectorTransport:
    """Never construct a socket, HTTP client, key loader or recording adapter."""

    def send(
        self,
        db: Database,
        permit: VectorPermit,
        node: FrozenVectorNode,
        wire: PreparedWire,
        attempt_id: str,
    ) -> FakeResponse:
        """Recheck full destination, bytes, signed identity, persisted attempt before fake send."""
        verify_predispatch(db, permit, node, wire)
        commit_dispatch(db, permit, attempt_id, wire)
        reply = self._safe_reply(node, wire)
        if HTTPStatus.MULTIPLE_CHOICES <= reply.status < HTTPStatus.BAD_REQUEST:
            msg = "vector_redirect_refused"
            raise VectorError(msg)
        if reply.status == HTTPStatus.SERVICE_UNAVAILABLE:
            msg = "vector_temporary_input_failure"
            raise VectorError(msg)
        if reply.status != HTTPStatus.OK:
            msg = "vector_protocol_failure"
            raise VectorError(msg)
        try:
            response = FakeResponse.model_validate_json(reply.body)
        except ValidationError:
            msg = "vector_invalid_response"
            raise VectorError(msg) from None
        expected_model = (
            "text-embedding-v4" if node.params.modality == "text" else "multimodal-embedding-v1"
        )
        if (
            response.model != expected_model
            or len(response.data) != 1
            or response.data[0].index != 0
            or len(response.data[0].embedding) != node.params.dimensions
        ):
            msg = "vector_response_mapping_invalid"
            raise VectorError(msg)
        return response

    def _safe_reply(self, node: FrozenVectorNode, wire: PreparedWire) -> FakeReply:
        try:
            return self._respond(node, wire)
        except (OSError, RuntimeError, ValueError, TypeError, struct.error):
            msg = "vector_fake_dispatch_failed"
            raise VectorError(msg) from None

    def _respond(self, node: FrozenVectorNode, wire: PreparedWire) -> FakeReply:
        """Generate invented deterministic vectors and usage, solely for contract testing."""
        seed = hashlib.sha256(wire.body).digest()
        vector = [float(seed[index % len(seed)] + 1) for index in range(node.params.dimensions)]
        # Round now so returned values and persistent canonical bytes are identical.
        rounded = struct.unpack(f"<{len(vector)}f", struct.pack(f"<{len(vector)}f", *vector))
        return FakeReply(
            body=json.dumps(
                {
                    "id": "fake_" + str(wire.frozen.payload_hash),
                    "object": "list",
                    "model": "text-embedding-v4"
                    if node.params.modality == "text"
                    else "multimodal-embedding-v1",
                    "data": [{"object": "embedding", "index": 0, "embedding": rounded}],
                    "usage": {"total_tokens": wire.frozen.token_bound},
                }
            ).encode()
        )
