# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run real sandbox cases alone before distributing the remaining collection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from xdist.scheduler.loadgroup import LoadGroupScheduling

if TYPE_CHECKING:
    from xdist.remote import Producer
    from xdist.workermanage import WorkerController

_SECURITY_GROUP = "custom-sandbox-security"
_SECURITY_PREFIX = "tests/operators/custom_sandbox/test_security.py::"


class ExclusiveSecurityScheduling(LoadGroupScheduling):
    """Preserve loadgroup semantics while fencing the sandbox group from ordinary work."""

    def __init__(self, config: pytest.Config, log: Producer | None = None) -> None:
        """Keep idle workers available and fail closed if any worker crashes."""
        super().__init__(config, log)
        self._exclusive = False
        self._aborted = False
        self._security_node: WorkerController | None = None
        config.pluginmanager.register(self, "datakeel-exclusive-security-scheduler")

    @property
    def tests_finished(self) -> bool:
        """Do not let xdist close idle workers while the final sandbox case is pending."""
        if self._aborted:
            return True
        return not self._exclusive and super().tests_finished

    @pytest.hookimpl
    def pytest_testnodedown(self, node: WorkerController, error: object | None) -> None:
        """Abort on every crash, including idle workers that have no reportable test item."""
        if error is None or self._aborted:
            return
        self._aborted = True
        self.config.hook.pytest_collectreport(
            report=pytest.CollectReport(
                nodeid=node.gateway.id,
                outcome="failed",
                longrepr="Worker crashed during isolated scheduling: " + str(error),
                result=[],
            )
        )

    def remove_node(self, node: WorkerController) -> str | None:
        """Never requeue unfinished work after a crash has invalidated the run."""
        if not self._aborted:
            return super().remove_node(node)
        workload = self.assigned_work.pop(node)
        return next(
            (
                nodeid
                for unit in workload.values()
                for nodeid, completed in unit.items()
                if not completed
            ),
            None,
        )

    def _reschedule(self, node: WorkerController) -> None:
        if self._aborted:
            node.shutdown()
        elif not self._exclusive:
            super()._reschedule(node)

    def _start_parallel(self) -> None:
        for node in self.nodes:
            if (
                self.workqueue
                and not node.shutting_down
                and not self._pending_of(self.assigned_work[node])
            ):
                self._assign_work_unit(node)
        for node in self.nodes:
            self._reschedule(node)

    def mark_test_complete(
        self, node: WorkerController, item_index: int, duration: float = 0
    ) -> None:
        """Release ordinary work only after every sandbox test protocol has completed."""
        if self._aborted:
            return
        super().mark_test_complete(node, item_index, duration)
        if self._exclusive and node is self._security_node:
            security = self.assigned_work[node][_SECURITY_GROUP]
            if all(security.values()):
                self._exclusive = False
                self._start_parallel()

    def schedule(self) -> None:
        """Send the sandbox unit first, retaining every ordinary node for its second phase."""
        if self._aborted or self.collection is not None:
            for node in self.nodes:
                self._reschedule(node)
            return
        if not self._check_nodes_have_same_collection():
            self._aborted = True
            return
        self.collection = list(next(iter(self.registered_collections.values())))
        for nodeid in self.collection:
            scope = self._split_scope(nodeid)
            if nodeid.startswith(_SECURITY_PREFIX) and scope != _SECURITY_GROUP:
                message = "Sandbox cases require their declared exclusive worker group"
                raise RuntimeError(message)
            self.workqueue.setdefault(scope, {})[nodeid] = False
        if _SECURITY_GROUP not in self.workqueue:
            self._start_parallel()
            return
        self._exclusive = True
        self._security_node = self.nodes[0]
        self.workqueue.move_to_end(_SECURITY_GROUP, last=False)
        self._assign_work_unit(self._security_node)
        if self.workqueue:
            # xdist fetches nextitem before running the current case. This lookahead starts
            # only after the final security protocol finishes, allowing worker reuse.
            self._assign_work_unit(self._security_node)
        else:
            # A shutdown marker supplies nextitem=None for a security-only collection.
            self._security_node.shutdown()
