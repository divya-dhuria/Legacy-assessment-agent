from __future__ import annotations

import pytest
from pydantic import ValidationError

from laa.domain.enums import Visibility
from laa.domain.source import SourceObject


def make_source(**overrides: object) -> SourceObject:
    defaults: dict[str, object] = dict(
        schema_name="RATING",
        object_name="PKG_RATING_ENGINE",
        object_type="PACKAGE BODY",
        visibility=Visibility.VISIBLE_WITH_SOURCE,
    )
    defaults.update(overrides)
    return SourceObject(**defaults)  # type: ignore[arg-type]


def test_visible_with_source_accepts_readable_properties() -> None:
    source = make_source(
        visibility=Visibility.VISIBLE_WITH_SOURCE,
        line_count=120,
        source_available=True,
        content_hash="a" * 64,
    )
    assert source.line_count == 120


def test_inferred_only_requires_inferred_from() -> None:
    with pytest.raises(ValidationError):
        make_source(visibility=Visibility.INFERRED_ONLY, inferred_from=None)


def test_inferred_only_rejects_line_count() -> None:
    with pytest.raises(ValidationError):
        make_source(
            visibility=Visibility.INFERRED_ONLY,
            inferred_from="dependency:PKG_OTHER",
            line_count=10,
        )


def test_inferred_only_rejects_content_hash() -> None:
    with pytest.raises(ValidationError):
        make_source(
            visibility=Visibility.INFERRED_ONLY,
            inferred_from="dependency:PKG_OTHER",
            content_hash="a" * 64,
        )


def test_inferred_only_rejects_source_available_true() -> None:
    with pytest.raises(ValidationError):
        make_source(
            visibility=Visibility.INFERRED_ONLY,
            inferred_from="dependency:PKG_OTHER",
            source_available=True,
        )


def test_inferred_only_valid_minimal_row() -> None:
    source = make_source(
        visibility=Visibility.INFERRED_ONLY,
        inferred_from="dependency:PKG_OTHER",
    )
    assert source.source_available is False
    assert source.line_count is None
    assert source.content_hash is None


def test_visibility_has_no_default_so_absence_cannot_be_constructed() -> None:
    with pytest.raises(ValidationError):
        SourceObject(  # type: ignore[call-arg]
            schema_name="RATING",
            object_name="PKG_RATING_ENGINE",
            object_type="PACKAGE BODY",
        )
