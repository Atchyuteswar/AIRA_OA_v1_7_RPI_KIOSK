"""Application logging (rotating file + console)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from core.paths import logs_dir

_CONFIGURED = False


def setup(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    log = logging.getLogger("aira")
    if _CONFIGURED:
        return log
    log.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        fh = RotatingFileHandler(logs_dir() / "aira.log", maxBytes=1_000_000, backupCount=3,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    log.addHandler(ch)
    _CONFIGURED = True
    return log


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"aira.{name}")
