"""Enumerations shared across the domain model."""

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
    HALTED = "halted"  # deliberate stop, e.g. visibility gate


class ItemStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
