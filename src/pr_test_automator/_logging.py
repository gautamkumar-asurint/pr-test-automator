"""Lightweight stdlib-based logger used internally by the pipeline.

The package deliberately avoids depending on ``structlog`` or other third-party
logging libraries so it stays a minimal install. Consumers can override the
log level via the ``PR_TEST_AUTOMATOR_LOG_LEVEL`` environment variable or by
configuring the root logger themselves.
"""

from __future__ import annotations

import logging
import os
from typing import Any

_DEFAULT_LEVEL = logging.INFO
_ENV_LEVEL = "PR_TEST_AUTOMATOR_LOG_LEVEL"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s : %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_once() -> None:
    """Attach a single StreamHandler to our package logger root."""
    global _configured
    if _configured:
        return

    level_name = os.environ.get(_ENV_LEVEL, "").upper()
    level = getattr(logging, level_name, _DEFAULT_LEVEL) if level_name else _DEFAULT_LEVEL

    root = logging.getLogger("pr_test_automator")
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(handler)
    root.propagate = False
    _configured = True


class _ContextAdapter(logging.LoggerAdapter):
    """LoggerAdapter that appends ``key=value`` context to every message."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra: dict[str, Any] = kwargs.pop("extra", {}) or {}
        # Merge anything passed positionally as keyword args.
        bound = {**(self.extra or {}), **extra}
        if bound:
            tail = " ".join(f"{k}={v}" for k, v in bound.items())
            msg = f"{msg} | {tail}"
        return msg, kwargs


def get_logger(name: str) -> logging.LoggerAdapter:
    """Return a logger bound to ``name``, configured once on first call.

    Usage:
        logger = get_logger(__name__)
        logger.info("starting", extra={"pr": 42})
    """
    _configure_once()
    return _ContextAdapter(logging.getLogger(name), {})
