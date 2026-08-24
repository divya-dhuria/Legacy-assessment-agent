from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from laa.domain.enums import Confidence, ReviewState, RuleType
from laa.domain.rule import Rule


def make_rule(**overrides: object) -> Rule:
    defaults: dict[str, object] = dict(
        rule_id="BR-RATE-0001",
        natural_key="a" * 64,
        statement="Apply the surcharge when the policy is lapsed.",
        original_statement="Apply the surcharge when the policy is lapsed.",
        rule_type=RuleType.CALCULATION,
        module="rating",
        schema_name="RATING",
        source_object="PKG_RATING_ENGINE",
        source_unit="PRC_APPLY_LOADINGS",
        line_start=10,
        line_end=20,
        source_hash="b" * 64,
        data_elements=["policy.status"],
        confidence=Confidence.HIGH,
        extraction_run_id="run-1",
        model_id="claude-sonnet-5",
    )
    defaults.update(overrides)
    return Rule(**defaults)  # type: ignore[arg-type]


def test_round_trip_preserves_all_fields() -> None:
    original = make_rule(
        review_state=ReviewState.ACCEPTED,
        reviewer="jane.reviewer",
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
        reviewer_note="looks right",
        is_stale=True,
        duplicate_of="BR-RATE-0002",
    )
    restored = Rule(**original.model_dump())
    assert restored == original
    assert restored.data_elements == ["policy.status"]
    assert restored.reviewed_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_line_end_before_line_start_rejected() -> None:
    with pytest.raises(ValidationError):
        make_rule(line_start=20, line_end=10)


def test_line_start_below_one_rejected() -> None:
    with pytest.raises(ValidationError):
        make_rule(line_start=0, line_end=5)


def test_edited_without_statement_change_rejected() -> None:
    with pytest.raises(ValidationError):
        make_rule(
            review_state=ReviewState.EDITED,
            statement="same",
            original_statement="same",
            reviewer="jane",
            reviewed_at=datetime.now(UTC),
        )


def test_non_pending_requires_reviewer_and_reviewed_at() -> None:
    with pytest.raises(ValidationError):
        make_rule(review_state=ReviewState.ACCEPTED, reviewer=None, reviewed_at=None)


def test_rule_id_format_rejected() -> None:
    with pytest.raises(ValidationError):
        make_rule(rule_id="not-a-valid-id")


def test_reviewed_at_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError):
        make_rule(
            review_state=ReviewState.ACCEPTED,
            reviewer="jane",
            reviewed_at=datetime(2026, 1, 1),
        )


def test_reviewed_at_non_utc_offset_rejected() -> None:
    with pytest.raises(ValidationError):
        make_rule(
            review_state=ReviewState.ACCEPTED,
            reviewer="jane",
            reviewed_at=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5))),
        )


def test_duplicate_of_self_rejected() -> None:
    with pytest.raises(ValidationError):
        make_rule(rule_id="BR-RATE-0001", duplicate_of="BR-RATE-0001")


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        make_rule(unexpected_field="nope")
