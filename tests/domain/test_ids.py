from __future__ import annotations

from datetime import UTC, datetime

from laa.domain.enums import Confidence, ReviewState, RuleType
from laa.domain.ids import (
    match_existing,
    merge_extraction,
    natural_key,
    next_rule_id,
    normalize_span,
    source_hash,
)
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


# --- normalize_span / source_hash -------------------------------------------------


def test_normalize_span_strips_trailing_whitespace_and_blank_lines() -> None:
    lines = ["", "  ", "BEGIN  ", "  x := 1;", "END;   ", "", ""]
    assert normalize_span(lines) == "BEGIN\n  x := 1;\nEND;"


def test_source_hash_stable_for_equivalent_spans() -> None:
    a = ["BEGIN  ", "  x := 1;", "END;"]
    b = ["", "BEGIN", "  x := 1;", "END;", ""]
    assert source_hash(a) == source_hash(b)


def test_source_hash_changes_on_comment_change() -> None:
    a = ["x := 1; -- original"]
    b = ["x := 1; -- edited"]
    assert source_hash(a) != source_hash(b)


# --- natural_key --------------------------------------------------------------


def test_natural_key_stable_under_trivial_wording_differences() -> None:
    key_a = natural_key(
        "PKG_RATING_ENGINE",
        "PRC_APPLY_LOADINGS",
        RuleType.CALCULATION,
        "Apply the surcharge when the policy is lapsed.",
    )
    key_b = natural_key(
        "PKG_RATING_ENGINE",
        "PRC_APPLY_LOADINGS",
        RuleType.CALCULATION,
        "  APPLY the surcharge, when the policy is LAPSED   ",
    )
    assert key_a == key_b


def test_natural_key_differs_for_genuinely_different_rules() -> None:
    key_a = natural_key(
        "PKG_RATING_ENGINE",
        "PRC_APPLY_LOADINGS",
        RuleType.CALCULATION,
        "Apply the surcharge when the policy is lapsed.",
    )
    key_b = natural_key(
        "PKG_RATING_ENGINE",
        "PRC_APPLY_LOADINGS",
        RuleType.CALCULATION,
        "Reject the claim when the coverage has expired.",
    )
    assert key_a != key_b


# --- match_existing -------------------------------------------------------------


def test_match_existing_matches_on_natural_key() -> None:
    existing = make_rule(rule_id="BR-RATE-0001", natural_key="key-1", line_start=1, line_end=5)
    candidate = make_rule(
        rule_id="BR-RATE-9999", natural_key="key-1", line_start=100, line_end=105
    )
    assert match_existing(candidate, [existing]) is existing


def test_match_existing_falls_back_to_overlapping_line_range() -> None:
    existing = make_rule(
        rule_id="BR-RATE-0001",
        natural_key="key-old",
        source_unit="PRC_APPLY_LOADINGS",
        line_start=10,
        line_end=20,
    )
    candidate = make_rule(
        rule_id="BR-RATE-9999",
        natural_key="key-new",
        source_unit="PRC_APPLY_LOADINGS",
        line_start=15,
        line_end=25,
    )
    assert match_existing(candidate, [existing]) is existing


def test_match_existing_returns_none_when_nothing_matches() -> None:
    existing = make_rule(
        rule_id="BR-RATE-0001",
        natural_key="key-old",
        source_unit="PRC_APPLY_LOADINGS",
        line_start=10,
        line_end=20,
    )
    candidate = make_rule(
        rule_id="BR-RATE-9999",
        natural_key="key-new",
        source_unit="PRC_OTHER",
        line_start=100,
        line_end=105,
    )
    assert match_existing(candidate, [existing]) is None


# --- merge_extraction -----------------------------------------------------------


def test_merge_extraction_preserves_rule_id_and_review_state() -> None:
    matched = make_rule(
        rule_id="BR-RATE-0001",
        natural_key="key-1",
        review_state=ReviewState.ACCEPTED,
        reviewer="jane",
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    candidate = make_rule(
        rule_id="BR-RATE-9999",
        natural_key="key-1",
        line_start=50,
        line_end=60,
        source_hash="c" * 64,
        confidence=Confidence.LOW,
        extraction_run_id="run-2",
    )

    merged = merge_extraction(candidate, matched)

    assert merged.rule_id == "BR-RATE-0001"
    assert merged.natural_key == matched.natural_key
    assert merged.review_state == ReviewState.ACCEPTED
    assert merged.reviewer == "jane"
    assert merged.reviewed_at == matched.reviewed_at
    assert merged.line_start == 50
    assert merged.line_end == 60
    assert merged.confidence == Confidence.LOW
    assert merged.extraction_run_id == "run-2"


def test_merge_extraction_sets_is_stale_when_hash_differs() -> None:
    matched = make_rule(source_hash="a" * 64)
    candidate = make_rule(source_hash="b" * 64)
    merged = merge_extraction(candidate, matched)
    assert merged.is_stale is True


def test_merge_extraction_not_stale_when_hash_matches() -> None:
    same_hash = "x" * 64
    matched = make_rule(source_hash=same_hash)
    candidate = make_rule(source_hash=same_hash)
    merged = merge_extraction(candidate, matched)
    assert merged.is_stale is False


def test_reviewed_rule_statement_and_original_statement_survive_reextraction() -> None:
    matched = make_rule(
        statement="Edited human-reviewed wording.",
        original_statement="Apply the surcharge when the policy is lapsed.",
        review_state=ReviewState.EDITED,
        reviewer="jane",
        reviewed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    candidate = make_rule(
        statement="Apply the surcharge when the policy is lapsed (re-extracted).",
        original_statement="Apply the surcharge when the policy is lapsed (re-extracted).",
    )

    merged = merge_extraction(candidate, matched)

    assert merged.statement == "Edited human-reviewed wording."
    assert merged.original_statement == "Apply the surcharge when the policy is lapsed."


def test_unreviewed_rule_takes_candidate_statement_and_original() -> None:
    matched = make_rule(
        statement="First-pass wording.",
        original_statement="First-pass wording.",
        review_state=ReviewState.PENDING,
    )
    candidate = make_rule(
        statement="Refined wording from re-extraction.",
        original_statement="Refined wording from re-extraction.",
    )

    merged = merge_extraction(candidate, matched)

    assert merged.statement == "Refined wording from re-extraction."
    assert merged.original_statement == "Refined wording from re-extraction."


# --- next_rule_id ----------------------------------------------------------------


def test_next_rule_id_starts_at_one() -> None:
    assert next_rule_id("RATE", []) == "BR-RATE-0001"


def test_next_rule_id_gapless_sequential() -> None:
    existing = ["BR-RATE-0001", "BR-RATE-0002", "BR-RATE-0003"]
    assert next_rule_id("RATE", existing) == "BR-RATE-0004"


def test_next_rule_id_ignores_other_prefixes() -> None:
    existing = ["BR-CLAIM-0001", "BR-CLAIM-0002", "BR-RATE-0001"]
    assert next_rule_id("RATE", existing) == "BR-RATE-0002"


def test_next_rule_id_no_collision_when_ids_out_of_order() -> None:
    existing = ["BR-RATE-0003", "BR-RATE-0001", "BR-RATE-0002"]
    new_id = next_rule_id("RATE", existing)
    assert new_id == "BR-RATE-0004"
    assert new_id not in existing
