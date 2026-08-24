# Legacy Assessment Agent

Internal delivery accelerator for fixed-fee legacy system assessments. See
[`CLAUDE.md`](CLAUDE.md) for the full project brief.

## Install

```bash
uv sync
```

## Run

```bash
uv run laa --help
```

Global options (set before the subcommand): `--log-level` (default `INFO`),
`--log-format` (`console` default, or `json`).

## Commands

| Command | Description |
|---|---|
| `laa init --engagement <id>` | Scaffold a new engagement directory. |
| `laa run --engagement <id>` | Execute the assessment pipeline. |
| `laa status --engagement <id>` | Show run and stage state for an engagement. |
| `laa report --engagement <id>` | Generate the assessment deliverable. |

Example:

```bash
uv run laa status --engagement demo
uv run laa --log-format json run --engagement demo --stage inventory
```

## Develop

```bash
uv run pytest
uv run ruff check
uv run mypy laa/
```
