"""Shared arrangements for the suite."""

from __future__ import annotations

import pytest

from romgoblin import screenscraper


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries, without the waits.

    The same number of attempts - the count is what the behaviour depends on -
    with the delays set to zero. Left alone the suite spends fourteen seconds
    asleep, which is how a suite stops being run.
    """
    monkeypatch.setattr(screenscraper, "RETRY_DELAYS", (0.0,) * len(screenscraper.RETRY_DELAYS))
