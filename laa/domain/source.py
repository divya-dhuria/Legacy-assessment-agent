"""SourceObject: the catalogue-derived inventory record.

An object that is known to exist but was not readable is recorded as
`INFERRED_ONLY`, never silently omitted — see CLAUDE.md's constraint on
never reporting a floor as a total.
"""

from pydantic import BaseModel, ConfigDict, model_validator

from laa.domain.enums import Visibility


class SourceObject(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    schema_name: str
    object_name: str
    object_type: str
    visibility: Visibility
    inferred_from: str | None = None
    line_count: int | None = None
    source_available: bool = False
    status: str | None = None
    module: str | None = None
    content_hash: str | None = None

    @model_validator(mode="after")
    def _inferred_only_cannot_claim_readable_properties(self) -> "SourceObject":
        if self.visibility == Visibility.INFERRED_ONLY:
            if self.inferred_from is None:
                raise ValueError("visibility INFERRED_ONLY requires inferred_from to be set")
            if self.line_count is not None:
                raise ValueError("visibility INFERRED_ONLY forbids line_count")
            if self.content_hash is not None:
                raise ValueError("visibility INFERRED_ONLY forbids content_hash")
            if self.source_available:
                raise ValueError("visibility INFERRED_ONLY forbids source_available=True")
        return self
