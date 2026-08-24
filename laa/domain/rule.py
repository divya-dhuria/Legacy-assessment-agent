"""The Rule record: the domain model every later epic reads or writes.

Provenance (source_object/source_unit/line range/source_hash) and review state
(review_state/reviewer/reviewed_at) are both mandatory parts of this model — see
CLAUDE.md's non-negotiable constraints on provenance and human review.
"""

import re
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from laa.domain.enums import Confidence, ReviewState, RuleType

_RULE_ID_RE = re.compile(r"^BR-[A-Z]{2,6}-\d{4}$")


class Rule(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    rule_id: str
    natural_key: str
    statement: str
    original_statement: str
    rule_type: RuleType
    module: str
    schema_name: str
    source_object: str
    source_unit: str | None
    line_start: int
    line_end: int
    source_hash: str
    data_elements: list[str] = []
    confidence: Confidence
    extraction_run_id: str
    model_id: str
    review_state: ReviewState = ReviewState.PENDING
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    reviewer_note: str | None = None
    is_stale: bool = False
    duplicate_of: str | None = None

    @field_validator("rule_id")
    @classmethod
    def _rule_id_format(cls, value: str) -> str:
        if not _RULE_ID_RE.match(value):
            raise ValueError(f"rule_id {value!r} does not match ^BR-[A-Z]{{2,6}}-\\d{{4}}$")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def _reviewed_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("reviewed_at must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def _line_range(self) -> "Rule":
        if self.line_start < 1 or self.line_end < 1:
            raise ValueError("line_start and line_end must be >= 1")
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self

    @model_validator(mode="after")
    def _edited_requires_change(self) -> "Rule":
        if self.review_state == ReviewState.EDITED and self.statement == self.original_statement:
            raise ValueError("review_state EDITED requires statement != original_statement")
        return self

    @model_validator(mode="after")
    def _reviewed_requires_reviewer(self) -> "Rule":
        if self.review_state != ReviewState.PENDING and (
            self.reviewer is None or self.reviewed_at is None
        ):
            raise ValueError(
                "review_state != PENDING requires both reviewer and reviewed_at to be set"
            )
        return self

    @model_validator(mode="after")
    def _duplicate_not_self(self) -> "Rule":
        if self.duplicate_of is not None and self.duplicate_of == self.rule_id:
            raise ValueError("duplicate_of must not equal rule_id")
        return self
