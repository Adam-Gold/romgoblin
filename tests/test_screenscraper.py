"""The client's refusals, and the quota arithmetic ScreenScraper requires of us.

The service is not under test; a recorded response shape is. What is tested is
everything this project owns — which is, almost entirely, the refusals.
"""

from __future__ import annotations

import pytest

from romgoblin import screenscraper


def response(*, used: int = 0, allowed: int = 0, medias: list | None = None) -> dict:
    return {
        "response": {
            "ssuser": {"requeststoday": str(used), "maxrequestsperday": str(allowed)},
            "jeu": {"medias": medias or []},
        }
    }


def test_quota_is_read_from_the_response() -> None:
    quota = screenscraper.quota_of(response(used=30, allowed=100))
    assert (quota.used, quota.allowed, quota.remaining) == (30, 100, 70)


def test_a_spent_quota_stops_the_run() -> None:
    """Their documentation makes this the software's obligation, so it gets a
    test that fails if somebody removes it."""
    with pytest.raises(screenscraper.QuotaExhausted):
        screenscraper.Quota(used=100, allowed=100).require_headroom()


def test_an_unknown_allowance_does_not_stop_the_run() -> None:
    """An anonymous caller gets a small allowance rather than none, and the
    server is the authority on when it ends. Guessing zero here would refuse to
    fetch anything at all."""
    screenscraper.Quota(used=0, allowed=0).require_headroom()


def test_a_response_with_no_quota_fields_is_not_a_crash() -> None:
    assert screenscraper.quota_of({}) == screenscraper.Quota(used=0, allowed=0)


def test_box_art_is_the_only_medium_taken() -> None:
    """A response also offers screenshots, titles, logos and video. Taking
    whichever comes first is how a screenshot ends up where a cover belongs."""
    payload = response(
        medias=[
            {"type": "ss", "url": "https://example.invalid/screenshot.png"},
            {"type": "wheel", "url": "https://example.invalid/logo.png"},
            {"type": "box-2D", "url": "https://example.invalid/cover.png"},
        ]
    )
    assert screenscraper.cover_url(payload) == "https://example.invalid/cover.png"


def test_a_game_with_no_box_art_yields_nothing_rather_than_something_else() -> None:
    payload = response(medias=[{"type": "ss", "url": "https://example.invalid/screenshot.png"}])
    assert screenscraper.cover_url(payload) is None


def test_credentials_refuse_when_the_build_has_no_developer_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Until ScreenScraper grants them, the tool says so rather than sending a
    request it knows will be rejected."""
    monkeypatch.setattr(screenscraper, "DEV_ID", "")
    with pytest.raises(screenscraper.CredentialsMissing, match="developer credentials"):
        screenscraper.Credentials.resolve()


def test_member_credentials_are_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """No account means the anonymous allowance, not a refusal."""
    monkeypatch.setattr(screenscraper, "DEV_ID", "dev")
    monkeypatch.setattr(screenscraper, "DEV_PASSWORD", "secret")
    monkeypatch.delenv("SCREENSCRAPER_SSID", raising=False)
    monkeypatch.delenv("SCREENSCRAPER_SSPASSWORD", raising=False)
    assert screenscraper.Credentials.resolve().ssid == ""
