# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate a media dataset from lavfi without storing recordings in the repository."""

import argparse
from pathlib import Path

from rich.console import Console

from datakeel.sample_media import generate_media


def main() -> None:
    """Write generated recordings into an explicitly selected local directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    Console().print(str(generate_media(args.output)), markup=False)


if __name__ == "__main__":
    main()
