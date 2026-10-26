# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stable facade for the single native data asset authorization policy."""

from datakeel.storage.data_asset_access import require_access, require_access_in_session

__all__ = ["require_access", "require_access_in_session"]
