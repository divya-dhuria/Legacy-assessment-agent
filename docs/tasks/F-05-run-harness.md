# F-05 — Run harness

**Depends on:** F-03, F-04
**Goal:** pipeline execution that survives failure at object 340 of 378.

Real runs process hundreds of objects, call paid APIs, and take hours. Restarting from
zero is not acceptable, and one unparseable object must not halt the run.

---

## `laa/runner/context.py`

```python
@dataclass
class RunContext:
    engagement_id: str
    run_id: str
    config: EngagementConfig
    engagement_dir: Path
    conn: sqlite3.Connection
    runs: RunRepo
    stages: StageRepo
    sources: SourceRepo
    rules: RuleRepo
    costs: CostRepo
```

Stages **never** open their own connection or read config from disk. Everything arrives
through the context.

---

## `laa/runner/stage.py`

```python
class Stage(Protocol):
    name: str
    depends_on: list[str]

    def plan(self, ctx: RunContext) -> list[str]:
        """Item keys this stage will process. Empty list = single-shot stage."""

    def execute_item(self, ctx: RunContext, item_key: str) -> None:
        """Process one item. Raise to signal item failure."""
```

Single-shot stages return `[]` from `plan` and do their work in `execute_item`, which is
called once with `item_key=""`.

Item keys must be stable across runs — for Epic 1 onward, `SCHEMA.OBJECT_NAME`, not an
index. Resume depends on it.

---

## `laa/runner/pipeline.py`

### Registry and ordering

```python
def register(stage: Stage) -> None: ...
def resolve_order(stages: list[Stage]) -> list[Stage]: ...
```

Topological sort over `depends_on`. Reject cycles at registration with a message naming
the cycle. Reject a `depends_on` referencing an unregistered stage.

### Execution

```python
def run_pipeline(ctx: RunContext, only: str | None = None,
                 resume: bool = False, force: bool = False,
                 failure_threshold: float = 0.10) -> RunStatus: ...
```

Per stage:

1. If `resume` and the stage is `COMPLETED` and not `force` — skip, log at info
2. Write `stage_execution` as `RUNNING`, call `plan()`, record `items_total`
3. Determine outstanding items: all keys, minus those already `DONE` for this
   `(run_id, stage_name)` — unless `force`, which re-processes everything
4. For each item: call `execute_item`, mark `DONE` on success. On exception, log with
   the item key, increment `attempts`, record the error, mark `FAILED`, **continue to
   the next item**
5. After all items: if `items_failed / items_total > failure_threshold`, mark the stage
   `FAILED` and stop the pipeline. Otherwise mark `COMPLETED`
6. Log `items_total`, `items_done`, `items_failed`, elapsed seconds, and accumulated
   cost for the run so far

**One failing item must never fail the stage.** The threshold exists so that systematic
failure still stops the run.

### Resume semantics

`--resume` continues the **most recent run** rather than starting a new one, so
`stage_item` rows remain valid. A fresh run without `--resume` gets a new `run_id` and
starts clean.

### Halting

A stage may raise `PipelineHalt` to stop deliberately rather than through failure — used
in Epic 1 by the visibility gate. Mark the run `HALTED`, not `FAILED`, and surface the
halt reason. This is a controlled stop, and `laa status` must show it as distinct from an
error.

---

## CLI wiring

- `laa run --engagement <id>` — all stages in order, new run
- `laa run --engagement <id> --stage <name>` — that stage plus any unmet dependencies
- `laa run --engagement <id> --resume` — continue latest run, skip completed work
- `laa run --engagement <id> --force` — re-process regardless of checkpoints

`laa status --engagement <id>` shows, for the latest run: run ID, status, per-stage
status with `items_done / items_total`, failure counts, elapsed, and total cost.

---

## Register a `noop` stage

So the harness is testable end-to-end before Epic 1 exists:

```python
class NoopStage:
    name = "noop"
    depends_on: list[str] = []

    def plan(self, ctx: RunContext) -> list[str]:
        return [f"item-{i}" for i in range(5)]

    def execute_item(self, ctx: RunContext, item_key: str) -> None:
        ...
```

`laa run --engagement <id>` must complete successfully against it.

---

## Acceptance

- [ ] Stages execute in dependency order
- [ ] A dependency cycle is rejected at registration, naming the cycle
- [ ] `depends_on` referencing an unregistered stage is rejected
- [ ] `--stage` runs unmet dependencies first
- [ ] Killing a run mid-stage and re-running with `--resume` processes only outstanding
      items (test with a stage that raises on the 3rd of 5 items, then resumes)
- [ ] A single failing item does not fail the stage
- [ ] Exceeding `failure_threshold` fails the stage and stops the pipeline
- [ ] `PipelineHalt` produces `HALTED`, distinct from `FAILED`, with the reason surfaced
- [ ] `--force` re-processes items already marked `DONE`
- [ ] `laa status` shows per-stage progress and item counts
- [ ] Every log line during a run carries `engagement_id`, `run_id`, `stage`

## Out of scope

No real stages. `noop` only.
