from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run every test from a throwaway directory so CLI/logging side effects
    (e.g. engagements/<id>/logs/) never touch the repo."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
