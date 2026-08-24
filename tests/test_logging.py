from __future__ import annotations

import json
import logging
from pathlib import Path

import structlog

from laa.logging import configure_logging, log_context


def test_configure_logging_console_uses_console_renderer() -> None:
    configure_logging("INFO", "console")
    root = logging.getLogger()
    formatter = root.handlers[0].formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
    assert isinstance(formatter.processors[-1], structlog.dev.ConsoleRenderer)


def test_configure_logging_json_uses_json_renderer() -> None:
    configure_logging("INFO", "json")
    root = logging.getLogger()
    formatter = root.handlers[0].formatter
    assert isinstance(formatter, structlog.stdlib.ProcessorFormatter)
    assert isinstance(formatter.processors[-1], structlog.processors.JSONRenderer)


def test_configure_logging_writes_json_lines_to_file(tmp_path: Path) -> None:
    log_file = tmp_path / "engagement" / "logs" / "run-1.jsonl"
    configure_logging("INFO", "console", log_file)

    log = structlog.get_logger()
    log.info("hello", key="value")

    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "hello"
    assert payload["key"] == "value"
    assert "timestamp" in payload
    assert payload["level"] == "info"


def test_configure_logging_file_sink_is_json_even_with_console_format(tmp_path: Path) -> None:
    log_file = tmp_path / "run.jsonl"
    configure_logging("INFO", "console", log_file)

    log = structlog.get_logger()
    log.info("hello")

    line = log_file.read_text(encoding="utf-8").strip()
    parsed = json.loads(line)
    assert parsed["event"] == "hello"


def test_log_context_binds_and_unbinds() -> None:
    configure_logging("INFO", "json")

    assert structlog.contextvars.get_contextvars() == {}

    with log_context(engagement_id="demo", run_id="r1", stage="init"):
        bound = structlog.contextvars.get_contextvars()
        assert bound == {"engagement_id": "demo", "run_id": "r1", "stage": "init"}

    assert structlog.contextvars.get_contextvars() == {}


def test_log_context_unbinds_on_exception() -> None:
    configure_logging("INFO", "json")

    class BoomError(Exception):
        pass

    try:
        with log_context(engagement_id="demo", run_id="r1", stage="init"):
            raise BoomError("bang")
    except BoomError:
        pass

    assert structlog.contextvars.get_contextvars() == {}


def test_log_context_nested_does_not_leak() -> None:
    configure_logging("INFO", "json")

    with log_context(engagement_id="demo", run_id="r1", stage="outer"):
        with log_context(stage="inner"):
            assert structlog.contextvars.get_contextvars()["stage"] == "inner"
        assert structlog.contextvars.get_contextvars()["stage"] == "outer"

    assert structlog.contextvars.get_contextvars() == {}
