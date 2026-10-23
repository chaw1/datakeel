# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public structural interfaces for extending the standard command parser."""

import argparse
from typing import Protocol


class CommandGroup(Protocol):
    """Accept named child parsers without depending on argparse's private classes."""

    def add_parser(self, name: str) -> argparse.ArgumentParser:
        """Create one parser under an existing command group."""
        ...
