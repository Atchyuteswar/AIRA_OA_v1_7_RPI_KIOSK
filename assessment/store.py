"""Crash-safe JSON persistence.

v1.3 wrote records with ``Path.write_text``; a crash or power cut mid-write
left a truncated JSON file that later failed to load and silently vanished
from the history. Writes here go to a temp file in the same folder, are
fsync'd, then atomically renamed over the target.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from core import log as _log

_LOG = _log.get("store")


def write_json_atomic(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False, default=_default)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as exc:
        _LOG.warning("Could not read %s: %s", path, exc)
        return default


def _default(obj):
    """Make NumPy scalars/arrays JSON-serialisable."""
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")
