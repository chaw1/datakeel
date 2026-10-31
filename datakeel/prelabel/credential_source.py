# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve a cloud model credential at call time from the environment or the system keychain.

Only the variable or keychain account *name* is ever stored. The secret value lives in memory
for the duration of one run and is never written to the database, logs, lineage or responses.
"""

import shutil
import subprocess  # Fixed argv to the platform keychain tool, never a shell.
import sys
from collections.abc import Callable
from contextvars import ContextVar

from pydantic import SecretStr

from datakeel.core.prelabel_models import CloudModelConfig
from datakeel.core.settings import get_settings

KeychainReader = Callable[[str], str | None]
_KEYCHAIN_TIMEOUT_SECONDS = 10


def _macos_keychain(account: str) -> str | None:
    tool = shutil.which("security")
    if sys.platform != "darwin" or tool is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603  # argv is fixed; account is a validated env-style name.
            [tool, "find-generic-password", "-a", account, "-w"],
            capture_output=True,
            text=True,
            timeout=_KEYCHAIN_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


_KEYCHAIN: ContextVar[KeychainReader] = ContextVar("prelabel_keychain", default=_macos_keychain)


def use_keychain(reader: KeychainReader) -> None:
    """Replace the keychain reader for the current context (tests never touch a real keychain)."""
    _KEYCHAIN.set(reader)


def resolve_credential(config: CloudModelConfig) -> SecretStr | None:
    """Read the configured environment variable, or the keychain account of the same name."""
    if config.credential_source == "env":
        return get_settings().extraction_key(config.credential_env)
    value = _KEYCHAIN.get()(config.credential_env)
    return SecretStr(value) if value else None
