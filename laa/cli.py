"""Typer entrypoint. Commands are stubs: they configure logging, log a bound
event, and return. Domain logic lands in later tasks."""

from __future__ import annotations

import uuid
from pathlib import Path

import structlog
import typer

from laa.logging import configure_logging, log_context

app = typer.Typer(add_completion=False, no_args_is_help=True)
log = structlog.get_logger()


@app.callback()
def main(
    ctx: typer.Context,
    log_level: str = typer.Option("INFO", "--log-level", help="Logging level."),
    log_format: str = typer.Option(
        "console", "--log-format", help="Console renderer: 'console' or 'json'."
    ),
) -> None:
    """Legacy Assessment Agent."""
    ctx.obj = {"log_level": log_level, "log_format": log_format}


def _start(ctx: typer.Context, engagement: str, stage: str) -> str:
    """Configure logging for a command scoped to an engagement and return a run id."""
    run_id = uuid.uuid4().hex
    log_file = Path("engagements") / engagement / "logs" / f"run-{run_id}.jsonl"
    configure_logging(ctx.obj["log_level"], ctx.obj["log_format"], log_file)
    return run_id


EngagementOpt = typer.Option(..., "--engagement", help="Engagement id.")


@app.command()
def init(
    ctx: typer.Context,
    engagement: str = EngagementOpt,
    path: Path = typer.Option(Path("engagements"), "--path"),
) -> None:
    """Scaffold a new engagement directory."""
    run_id = _start(ctx, engagement, "init")
    with log_context(engagement_id=engagement, run_id=run_id, stage="init"):
        log.info("init.requested", path=str(path))


@app.command()
def run(
    ctx: typer.Context,
    engagement: str = EngagementOpt,
    stage: str | None = typer.Option(None, "--stage"),
    resume: bool = typer.Option(False, "--resume"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Execute the assessment pipeline."""
    resolved_stage = stage or "all"
    run_id = _start(ctx, engagement, resolved_stage)
    with log_context(engagement_id=engagement, run_id=run_id, stage=resolved_stage):
        log.info("run.requested", resume=resume, force=force)


@app.command()
def status(ctx: typer.Context, engagement: str = EngagementOpt) -> None:
    """Show run and stage state for an engagement."""
    run_id = _start(ctx, engagement, "status")
    with log_context(engagement_id=engagement, run_id=run_id, stage="status"):
        log.info("status.requested")


@app.command()
def report(
    ctx: typer.Context,
    engagement: str = EngagementOpt,
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Generate the assessment deliverable."""
    run_id = _start(ctx, engagement, "report")
    with log_context(engagement_id=engagement, run_id=run_id, stage="report"):
        log.info("report.requested", output=str(output) if output else None)


if __name__ == "__main__":
    app()
