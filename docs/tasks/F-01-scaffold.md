# F-01 — Repo scaffold, CLI, logging

**Depends on:** nothing
**Goal:** a runnable CLI skeleton with structured logging. No domain logic.

---

## Build

### Directory tree

Create the **full** structure now, including packages that stay empty until later tasks.
F-02 through F-05 assume these exist.

```
.
├── CLAUDE.md                        (already present)
├── README.md
├── pyproject.toml
├── .gitignore
├── docs/
│   └── tasks/                       (already present)
│       └── PROGRESS.md              create, empty
├── laa/
│   ├── __init__.py                  __version__ = "0.1.0"
│   ├── cli.py
│   ├── logging.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── models.py                stub — F-04
│   │   └── loader.py                stub — F-04
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── enums.py                 stub — F-02
│   │   ├── rule.py                  stub — F-02
│   │   ├── source.py                stub — F-02
│   │   └── ids.py                   stub — F-02
│   ├── store/
│   │   ├── __init__.py
│   │   ├── db.py                    stub — F-03
│   │   ├── repositories.py          stub — F-03
│   │   └── migrations/
│   │       └── .gitkeep             001_initial.sql lands in F-03
│   └── runner/
│       ├── __init__.py
│       ├── context.py               stub — F-05
│       ├── stage.py                 stub — F-05
│       └── pipeline.py              stub — F-05
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_cli.py
│   ├── test_logging.py
│   ├── domain/__init__.py
│   ├── store/__init__.py
│   ├── config/__init__.py
│   └── runner/__init__.py
└── engagements/                     gitignored, created at runtime by F-04
    └── .gitkeep
```

Stub modules contain only a module docstring naming the task that fills them. Do **not**
write placeholder classes or functions — an empty stub is honest, a fake implementation
is misleading.

`engagements/` is created but gitignored except for `.gitkeep`. It holds client source
and must never be committed.

### `pyproject.toml`

`uv`-managed, Python 3.11+.

Runtime: `typer`, `pydantic>=2`, `pyyaml`, `structlog`
Dev: `pytest`, `pytest-cov`, `ruff`, `mypy`, `types-pyyaml`

Console script `laa` → `laa.cli:app`.

Ruff: line length 100, select `E,F,I,N,UP,B,SIM`.
Mypy: strict on `laa.domain.*` and `laa.store.*`, default elsewhere.

### `.gitignore`

Must include `engagements/` — that directory holds client source and must never be
committed. Also `.venv/`, `__pycache__/`, `*.db`, `.coverage`, `.pytest_cache/`.

### `laa/cli.py`

Typer app with four commands, all stubs that log and exit cleanly:

```python
@app.command()
def init(engagement: str, path: Path = Path("engagements")) -> None:
    """Scaffold a new engagement directory."""

@app.command()
def run(engagement: str, stage: str | None = None,
        resume: bool = False, force: bool = False) -> None:
    """Execute the assessment pipeline."""

@app.command()
def status(engagement: str) -> None:
    """Show run and stage state for an engagement."""

@app.command()
def report(engagement: str, output: Path | None = None) -> None:
    """Generate the assessment deliverable."""
```

Global options via a Typer callback: `--log-level`, `--log-format`.

### `laa/logging.py`

Two renderers selected by `--log-format`:

- `console` (default) — `structlog.dev.ConsoleRenderer`, human-readable
- `json` — `structlog.processors.JSONRenderer`, one object per line

When an engagement is in scope, also write JSON lines to
`engagements/<id>/logs/run-<run_id>.jsonl` regardless of console format. Console and
file sinks are independent.

Bind `engagement_id`, `run_id`, `stage` via `structlog.contextvars.bind_contextvars` —
**not** by threading them through call signatures. Provide:

```python
def configure_logging(level: str, fmt: str, log_file: Path | None = None) -> None: ...

@contextmanager
def log_context(**kwargs: str) -> Iterator[None]: ...
```

Include an ISO-8601 UTC timestamp processor and `structlog.processors.add_log_level`.

### `README.md`

Install, run, and the four commands. Keep it short.

---

## Acceptance

- [ ] `uv run laa --help` lists `init`, `run`, `status`, `report`
- [ ] `uv run laa status --engagement demo` runs, logs a bound event, exits 0
- [ ] `--log-format json` produces valid single-line JSON per event
- [ ] `log_context` binds and unbinds correctly, including on exception
- [ ] `ruff check` and `mypy laa/` clean
- [ ] `.gitignore` contains `engagements/`
- [ ] Every package directory in the tree above exists with an `__init__.py`
- [ ] `python -c "import laa.domain.rule, laa.store.db, laa.runner.pipeline"` succeeds
      (stubs import cleanly)
- [ ] `laa.__version__` is readable

## Tests

- `configure_logging` with each format produces the expected renderer
- `log_context` unbinds on exception (nested contexts do not leak)
- CLI smoke test per command via Typer's `CliRunner`

## Out of scope

No config loading, no database, no domain models, no engagement scaffolding.
Commands log and return. Stub modules stay empty.

**Note on the two scaffolds:** this task creates the *repo* structure, once.
F-04 implements `scaffold()`, which creates a per-*engagement* working directory
(`engagements/<id>/`) each time a client engagement starts. Do not implement the
latter here.
