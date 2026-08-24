# F-04 — Engagement config

**Depends on:** F-01, F-03
**Goal:** one YAML file defines scope, modules, access expectations, and boundaries.

---

## Config shape

`engagements/<id>/engagement.yaml`

```yaml
engagement:
  id: acme-pas-2026
  client_name: "Acme Insurance"
  system_name: "Policy Administration System"
  snapshot_date: 2026-08-15

scope:
  stack: plsql
  schemas: [PAS_CORE, PAS_RATING, PAS_CLAIMS, PAS_PARTY, PAS_REF, PAS_BATCH]
  exclude_patterns: ["*_TMP", "PKG_DEBUG*"]
  vendor_supplied: ["PKG_VENDOR_*"]

modules:
  - name: "Rating Engine"
    prefix: RATE
    match:
      schemas: [PAS_RATING]
      name_patterns: ["PKG_RATING*", "FN_CALC_*"]
  - name: "Policy Lifecycle"
    prefix: LIFE
    match:
      name_patterns: ["PKG_POLICY*"]

access:
  expected_privilege: select_catalog   # dba | select_catalog | schema_owner | restricted
  require_full_visibility: true
  connection_env: ACME_ORACLE_DSN

deployment:
  boundary: client_vpc        # client_vpc | nuactis
  model_id: <model>

limits:
  max_cost_usd: 500
  max_tokens_per_run: 20000000
```

---

## `laa/config/models.py`

Pydantic models: `EngagementConfig`, `Scope`, `ModuleConfig`, `ModuleMatch`,
`AccessConfig`, `DeploymentConfig`, `Limits`. `extra="forbid"` throughout — a typo in a
key must fail loudly, not be silently ignored.

### Rules

- `modules[].prefix` — unique across modules, `^[A-Z]{2,6}$`. Feeds rule IDs.
- `modules[].name` — unique.
- `deployment.boundary` — **required, no default.** Forcing an explicit per-engagement
  choice is deliberate.
- `access.expected_privilege` — **required, no default.**
- `access.require_full_visibility` — defaults `true`.
- `access.connection_env` — names an environment variable. **Reject any config
  containing an inline credential**: fail if a value matches a DSN or password pattern
  (`.*/.*@.*`, or keys named `password`, `pwd`, `secret`, `dsn`). This file gets shared
  and reviewed; credentials must never be in it.
- `scope.stack` — only `plsql` accepted in V0. Reject others with a clear message
  rather than a validation error.

### Module resolution

```python
def resolve_module(self, object_name: str, schema_name: str) -> str: ...
```

- First matching module in **declaration order** wins
- A `match` block matches when the object satisfies `schemas` (if present) **and** any
  of `name_patterns` (if present); an empty `match` never matches
- Patterns are `fnmatch` globs, case-insensitive
- No match returns `"Unassigned"`

```python
def module_prefix(self, module_name: str) -> str: ...
```

`"Unassigned"` maps to prefix `UNAS`.

---

## `laa/config/loader.py`

```python
def load(path: Path) -> EngagementConfig: ...
def config_hash(path: Path) -> str: ...
def scaffold(engagement_id: str, target: Path) -> Path: ...
```

**`config_hash`** — SHA-256 over the *parsed* config canonicalized as JSON with sorted
keys, not over raw file bytes. Comment edits and key reordering must not change the hash;
a value change must.

**Validation errors** must be readable. Catch `ValidationError` and render as a list of
`field: message`, not a traceback.

**`scaffold`** creates:

```
engagements/<id>/
  engagement.yaml     commented template, valid as-is
  assessment.db       empty, migrated to current version
  logs/
  source/             gitignored — client source lands here
```

The template must load and validate without edits, using placeholder values.

---

## CLI wiring

`laa init --engagement <id>` calls `scaffold`, then reports the created path.
`laa status --engagement <id>` loads config, opens the DB, prints engagement identity
and current schema version.

Where a run's `config_hash` differs from the previous run's, **log a warning naming the
changed top-level sections**. Do not silently accept, and do not block.

---

## Acceptance

- [ ] `laa init --engagement demo` produces a config that loads and validates unedited
- [ ] Duplicate module prefixes, malformed prefixes, and duplicate names are rejected
- [ ] `resolve_module` respects declaration order
- [ ] `resolve_module` handles glob patterns case-insensitively
- [ ] `resolve_module` returns `"Unassigned"` on no match, and the caller logs a warning
- [ ] An empty `match` block never matches
- [ ] `config_hash` stable across comment edits and key reordering; changes on value edit
- [ ] A config containing an inline credential is rejected with a clear message
- [ ] `deployment.boundary` and `access.expected_privilege` missing → validation failure
- [ ] `stack: tsql` produces a clear "not supported in V0" message
- [ ] Unknown keys are rejected, not ignored

## Out of scope

No database connection to Oracle. `connection_env` is recorded, never used yet.
