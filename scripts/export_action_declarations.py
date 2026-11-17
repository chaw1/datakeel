# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate the closed frontend declaration view directly from active owners."""

import json
import sys

from datakeel.action_store.validation import validate_declarations
from datakeel.actions.file_declarations import active_declarations


def main() -> None:
    """Export closed widget and phrase data from the active declaration owners."""
    validate_declarations()
    data = {
        name: {
            "phrases": dict(value.phrases),
            "widget": value.widget,
            "titles": {
                locale: phrases[0][:1].upper() + phrases[0][1:] for locale, phrases in value.phrases
            },
        }
        for name, value in active_declarations().items()
    }
    sys.stdout.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
