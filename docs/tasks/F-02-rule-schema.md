# F-02 — Rule record schema

**Depends on:** F-01
**Goal:** the domain model everything else projects from.

> This is the most consequential task in Epic 0. Every later epic reads or writes this
> model. Changing it after Epic 3 means rebuilding. If any part of this spec seems
> wrong, stop and flag it rather than adapting it.

---

## `laa/domain/enums.py`

```python
from enum import StrEnum

class RuleType(StrEnum):
    VALIDATION = "validation"
    CALCULATION = "calculation"
    ROUTING = "routing"
    STATE_TRANSITION = "state_transition"
    CONSTRAINT = "constraint"

class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ReviewState(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    NEEDS_SME = "needs_sme"
    UNRESOLVED_DYNAMIC = "unresolved_dynamic"

class Visibility(StrEnum):
    VISIBLE_WITH_SOURCE = "visible_with_source"
    VISIBLE_NO_SOURCE = "visible_no_source"
    INFERRED_ONLY = "inferred_only"

class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"          # deliberate stop, e.g. visibility gate

class ItemStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
```

---

## `laa/domain/rule.py`

Pydantic v2 model, `model_config = ConfigDict(frozen=False, extra="forbid")`.

| Field | Type | Notes |
|---|---|---|
| `rule_id` | `str` | `BR-{PREFIX}-{NNNN}` |
| `natural_key` | `str` | SHA-256 hex, see below |
| `statement` | `str` | Current text; edited value once reviewed |
| `original_statement` | `str` | Verbatim extraction output. **Never mutated.** |
| `rule_type` | `RuleType` | |
| `module` | `str` | |
| `schema_name` | `str` | |
| `source_object` | `str` | e.g. `PKG_RATING_ENGINE` |
| `source_unit` | `str \| None` | e.g. `PRC_APPLY_LOADINGS` |
| `line_start` | `int` | 1-indexed, inclusive |
| `line_end` | `int` | 1-indexed, inclusive |
| `source_hash` | `str` | SHA-256 of the normalized cited span |
| `data_elements` | `list[str]` | Default `[]` |
| `confidence` | `Confidence` | |
| `extraction_run_id` | `str` | |
| `model_id` | `str` | Model name and version |
| `review_state` | `ReviewState` | Default `PENDING` |
| `reviewer` | `str \| None` | |
| `reviewed_at` | `datetime \| None` | UTC, timezone-aware |
| `reviewer_note` | `str \| None` | |
| `is_stale` | `bool` | Default `False` |
| `duplicate_of` | `str \| None` | Canonical rule ID in a duplicate group |

### Validators — enforce, don't document

1. `line_end >= line_start`; both `>= 1`
2. `review_state == EDITED` requires `statement != original_statement`
3. `review_state != PENDING` requires both `reviewer` and `reviewed_at`
4. `rule_id` matches `^BR-[A-Z]{2,6}-\d{4}$`
5. `reviewed_at`, if set, must be timezone-aware UTC
6. `duplicate_of`, if set, must not equal `rule_id`

---

## `laa/domain/source.py`

`SourceObject` — populated in Epic 1, defined now.

| Field | Type | Notes |
|---|---|---|
| `schema_name` | `str` | |
| `object_name` | `str` | |
| `object_type` | `str` | `PACKAGE`, `PACKAGE BODY`, `FUNCTION`, ... |
| `visibility` | `Visibility` | Required, no default |
| `inferred_from` | `str \| None` | Dependency record proving an `INFERRED_ONLY` object exists |
| `line_count` | `int \| None` | `None` when source unreadable |
| `source_available` | `bool` | Default `False` |
| `status` | `str \| None` | Oracle `VALID` / `INVALID` |
| `module` | `str \| None` | |
| `content_hash` | `str \| None` | |

**Validator:** `visibility == INFERRED_ONLY` requires `inferred_from` set, and forbids
`line_count`, `content_hash`, `source_available=True`. An object we cannot read must not
be able to claim readable properties.

---

## `laa/domain/ids.py`

### Source hash

```python
def normalize_span(lines: list[str]) -> str: ...
def source_hash(lines: list[str]) -> str: ...
```

Normalization before hashing: strip trailing whitespace per line, normalize line endings
to `\n`, drop leading and trailing blank lines. **Do not** strip comments or normalize
case — a comment change is a meaningful change to a business rule.

### Natural key

```python
def natural_key(source_object: str, source_unit: str | None,
                rule_type: RuleType, statement: str) -> str: ...
```

`fingerprint` = statement lowercased, punctuation stripped, whitespace collapsed to
single spaces, truncated to 120 chars.
Key = SHA-256 of `f"{source_object}|{source_unit or ''}|{rule_type}|{fingerprint}"`.

### Matching

```python
def match_existing(candidate: Rule, existing: list[Rule]) -> Rule | None: ...
```

In order:
1. Exact `natural_key` match within the same `source_object`
2. Same `source_object` + `source_unit` + `rule_type` **and** overlapping line range
   (`candidate.line_start <= existing.line_end and candidate.line_end >= existing.line_start`)

Return the first match, or `None`.

### Merge

```python
def merge_extraction(candidate: Rule, matched: Rule) -> Rule: ...
```

On match, produce a rule that:
- keeps `matched.rule_id` and `matched.natural_key`
- keeps `matched.review_state`, `reviewer`, `reviewed_at`, `reviewer_note`
- takes new `line_start`, `line_end`, `source_hash`, `confidence`,
  `extraction_run_id`, `model_id`, `data_elements`
- keeps `matched.statement` if the rule was reviewed; otherwise takes the candidate's
- always takes `candidate.original_statement` into a new record only when unreviewed —
  a reviewed rule's `original_statement` is historical and must not be overwritten
- sets `is_stale = True` when `candidate.source_hash != matched.source_hash`

**Why this matters:** a reviewer may spend 30 hours dispositioning 1,200 rules. When the
client later recovers missing source and extraction re-runs, that work must survive.
Without stable matching, every rule gets a new ID and the review is lost.

### Sequence allocation

```python
def next_rule_id(module_prefix: str, existing_ids: Iterable[str]) -> str: ...
```

Gapless per prefix, zero-padded to 4 digits. Must not collide under re-run.

---

## Acceptance

- [ ] Round-trip model → dict → model preserves every field including `datetime` and lists
- [ ] Each of the six validators has a test asserting it rejects the invalid case
- [ ] Two extractions with trivially different wording (punctuation, casing, whitespace)
      of the same rule produce the same natural key
- [ ] Two genuinely different rules in the same unit produce different natural keys
- [ ] `match_existing` matches on natural key, and falls back to overlapping line range
- [ ] `merge_extraction` preserves `rule_id` and review state, and sets `is_stale` only
      when `source_hash` differs
- [ ] A reviewed rule's `statement` and `original_statement` survive re-extraction
- [ ] `next_rule_id` is gapless per prefix and does not collide under re-run
- [ ] `SourceObject` rejects an `INFERRED_ONLY` row carrying `line_count` or `content_hash`
- [ ] No code path treats absence of a `SourceObject` row as equivalent to `INFERRED_ONLY`

## Out of scope

No persistence. Pure domain models and functions.
