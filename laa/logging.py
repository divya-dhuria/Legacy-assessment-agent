"""structlog configuration: console rendering plus an independent per-engagement
JSON-lines file sink."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import structlog

_SHARED_PROCESSORS: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def configure_logging(level: str, fmt: str, log_file: Path | None = None) -> None:
    """Configure structlog with a console renderer and, when `log_file` is given, an
    independent JSON-lines file sink. The file sink is always JSON regardless of `fmt`.
    """
    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console_renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer()
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                console_renderer,
            ],
            foreign_pre_chain=_SHARED_PROCESSORS,
        )
    )

    handlers: list[logging.Handler] = [console_handler]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(),
                ],
                foreign_pre_chain=_SHARED_PROCESSORS,
            )
        )
        handlers.append(file_handler)

    root_logger = logging.getLogger()
    root_logger.handlers = handlers
    root_logger.setLevel(level.upper())


@contextmanager
def log_context(**kwargs: str) -> Iterator[None]:
    """Bind key-value pairs to structlog's contextvars for the duration of the block,
    restoring the prior values on exit — including when the block raises."""
    tokens = structlog.contextvars.bind_contextvars(**kwargs)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
