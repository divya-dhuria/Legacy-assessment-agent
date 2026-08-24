from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from laa.cli import app

runner = CliRunner()


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "run", "status", "report"):
        assert command in result.output


def test_init_exits_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--engagement", "demo", "--path", str(tmp_path)])
    assert result.exit_code == 0


def test_run_exits_cleanly() -> None:
    result = runner.invoke(app, ["run", "--engagement", "demo"])
    assert result.exit_code == 0


def test_run_accepts_stage_resume_force() -> None:
    result = runner.invoke(
        app, ["run", "--engagement", "demo", "--stage", "inventory", "--resume", "--force"]
    )
    assert result.exit_code == 0


def test_status_exits_cleanly() -> None:
    result = runner.invoke(app, ["status", "--engagement", "demo"])
    assert result.exit_code == 0


def test_report_exits_cleanly() -> None:
    result = runner.invoke(app, ["report", "--engagement", "demo"])
    assert result.exit_code == 0


def test_status_writes_json_lines_log_file() -> None:
    result = runner.invoke(app, ["status", "--engagement", "demo"])
    assert result.exit_code == 0

    log_dir = Path("engagements") / "demo" / "logs"
    log_files = list(log_dir.glob("run-*.jsonl"))
    assert len(log_files) == 1

    lines = log_files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"event": "status.requested"' in lines[0]
    assert '"engagement_id": "demo"' in lines[0]


def test_log_format_json_produces_valid_single_line_json() -> None:
    import json

    result = runner.invoke(app, ["--log-format", "json", "status", "--engagement", "demo"])
    assert result.exit_code == 0

    output_lines = [line for line in result.output.strip().splitlines() if line]
    assert len(output_lines) == 1
    parsed = json.loads(output_lines[0])
    assert parsed["event"] == "status.requested"
    assert parsed["engagement_id"] == "demo"
