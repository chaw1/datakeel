# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure only the directly owned development worker on Darwin."""

import ctypes
import subprocess
import sys
from functools import cache

from datakeel.operators.custom_process import RuntimeFailureError

_PROC_PIDTASKINFO = 4
_MEBIBYTE = 1024 * 1024


class _TaskInfo(ctypes.Structure):
    # The system SDK declares six uint64 fields followed by twelve int32 fields.
    _fields_ = (
        ("virtual_size", ctypes.c_uint64),
        ("resident_size", ctypes.c_uint64),
        ("cpu_times", ctypes.c_uint64 * 4),
        ("statistics", ctypes.c_int32 * 12),
    )
    resident_size: int


@cache
def _library() -> ctypes.CDLL:
    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    library.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    library.proc_pidinfo.restype = ctypes.c_int
    return library


def memory_exceeded(process: subprocess.Popen[bytes], memory_mb: int) -> bool:
    """Fail closed on unreadable live workers; other POSIX hosts use worker limits."""
    if sys.platform != "darwin":
        return False
    try:
        info = _TaskInfo()
        received = _library().proc_pidinfo(
            process.pid, _PROC_PIDTASKINFO, 0, ctypes.byref(info), ctypes.sizeof(info)
        )
        if received == ctypes.sizeof(info) and info.resident_size > 0:
            return info.resident_size > memory_mb * _MEBIBYTE
    except (AttributeError, OSError) as error:
        msg = "Worker memory usage could not be verified"
        raise RuntimeFailureError(msg) from error
    # The worker may finish between the caller's poll and the native measurement.
    if process.poll() is not None:
        return False
    msg = "Worker memory usage could not be verified"
    raise RuntimeFailureError(msg)
