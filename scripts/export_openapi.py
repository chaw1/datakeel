# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Export the actual local application schema without persistent side effects."""

import json
import sys

from datakeel.api.app import create_app
from datakeel.storage.database import Database


def main() -> None:
    """Write machine-readable OpenAPI for the generated frontend client."""
    db = Database("sqlite://")
    try:
        schema = create_app(db).openapi()
        sys.stdout.write(json.dumps(schema, ensure_ascii=False, sort_keys=True) + "\n")
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
