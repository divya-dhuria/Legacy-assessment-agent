"""Rule identity: source hashing, natural-key fingerprinting, stable matching
across re-extraction, and rule-id sequence allocation.

Stable matching exists so that human review survives re-extraction: a reviewer
may spend 30 hours dispositioning 1,200 rules, and when source is recovered and
extraction re-runs, that work must not be discarded for a fresh set of IDs.
"""

import hashlib
import re
import string
from collections.abc import Iterable

from laa.domain.enums import ReviewState, RuleType
from laa.domain.rule import Rule

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation)
_RULE_ID_SEQ_RE = r"^BR-{prefix}-(\d{{4}})$"


def normalize_span(lines: list[str]) -> str:
    """Strip trailing whitespace per line, normalize line endings to '\\n', and
    drop leading/trailing blank lines. Comments and case are left untouched — a
    comment change is a meaningful change to a business rule."""
    stripped = [line.rstrip() for line in lines]
    start = 0
    end = len(stripped)
    while start < end and stripped[start] == "":
        start += 1
    while end > start and stripped[end - 1] == "":
        end -= 1
    return "\n".join(stripped[start:end])


def source_hash(lines: list[str]) -> str:
    return hashlib.sha256(normalize_span(lines).encode("utf-8")).hexdigest()


def _fingerprint(statement: str) -> str:
    lowered = statement.lower().translate(_PUNCTUATION_TABLE)
    collapsed = _WHITESPACE_RE.sub(" ", lowered).strip()
    return collapsed[:120]


def natural_key(
    source_object: str, source_unit: str | None, rule_type: RuleType, statement: str
) -> str:
    fingerprint = _fingerprint(statement)
    payload = f"{source_object}|{source_unit or ''}|{rule_type}|{fingerprint}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def match_existing(candidate: Rule, existing: list[Rule]) -> Rule | None:
    for rule in existing:
        if rule.source_object == candidate.source_object and (
            rule.natural_key == candidate.natural_key
        ):
            return rule

    for rule in existing:
        if (
            rule.source_object == candidate.source_object
            and rule.source_unit == candidate.source_unit
            and rule.rule_type == candidate.rule_type
            and candidate.line_start <= rule.line_end
            and candidate.line_end >= rule.line_start
        ):
            return rule

    return None


def merge_extraction(candidate: Rule, matched: Rule) -> Rule:
    reviewed = matched.review_state != ReviewState.PENDING
    merged = matched.model_dump()
    merged.update(
        line_start=candidate.line_start,
        line_end=candidate.line_end,
        source_hash=candidate.source_hash,
        confidence=candidate.confidence,
        extraction_run_id=candidate.extraction_run_id,
        model_id=candidate.model_id,
        data_elements=list(candidate.data_elements),
        statement=matched.statement if reviewed else candidate.statement,
        original_statement=(
            matched.original_statement if reviewed else candidate.original_statement
        ),
        is_stale=candidate.source_hash != matched.source_hash,
    )
    return Rule.model_validate(merged)


def next_rule_id(module_prefix: str, existing_ids: Iterable[str]) -> str:
    pattern = re.compile(_RULE_ID_SEQ_RE.format(prefix=re.escape(module_prefix)))
    max_seq = 0
    for existing_id in existing_ids:
        match = pattern.match(existing_id)
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return f"BR-{module_prefix}-{max_seq + 1:04d}"
