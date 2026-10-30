"""Filesystem locations.

v1.3 used paths relative to the current working directory, so launching the
app from a different folder silently created a second, empty ``data/`` tree
and patient history appeared to vanish. All paths here are anchored to the
project folder (or ``AIRA_DATA_DIR`` when set).
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    override = os.environ.get("AIRA_DATA_DIR")
    root = Path(override).expanduser().resolve() if override else PROJECT_ROOT / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def patients_dir() -> Path:
    return _sub("patients")


def sessions_dir() -> Path:
    return _sub("sessions")


def reports_dir() -> Path:
    return _sub("reports")


def logs_dir() -> Path:
    return _sub("logs")
