"""What the built distribution has to contain.

The release failed once on this and it is invisible from the source tree: the
file at stake is git-ignored, so nothing you can read in a clone tells you
whether a wheel would carry it.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def config() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_the_credentials_file_is_forced_into_every_distribution() -> None:
    """Hatchling honours .gitignore, and `_dev_credentials.py` is ignored on
    purpose - it holds the ScreenScraper developer pair, which must never be
    committed. Both rules are right; together they build a wheel that refuses on
    every user's machine.

    It must sit under `[tool.hatch.build]` rather than under a single target.
    `python -m build` with no arguments builds the sdist and then builds the
    wheel *from the extracted sdist*, so a file the sdist never carried cannot
    reach the wheel however the wheel target is configured. Exempting it for the
    wheel alone passed a local `build --wheel` and failed the release.
    """
    artifacts = config()["tool"]["hatch"]["build"].get("artifacts", [])
    assert "romgoblin/_dev_credentials.py" in artifacts


def test_nothing_else_is_exempted_from_the_ignore_rules() -> None:
    """The exemption exists for one file. A second entry means something else
    is being smuggled past .gitignore, and .gitignore here is what keeps ROMs,
    box art and credentials out of the package."""
    assert config()["tool"]["hatch"]["build"].get("artifacts", []) == [
        "romgoblin/_dev_credentials.py"
    ]
