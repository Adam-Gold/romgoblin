"""The client's refusals, and the quota arithmetic ScreenScraper requires of us.

The service is not under test; a recorded response shape is. What is tested is
everything this project owns — which is, almost entirely, the refusals.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from romgoblin import screenscraper

#: A real `jeuInfos.php` response, recorded once against the live service and
#: committed so the parsing has something honest to work against. Pokemon
#: Crystal, matched by CRC32 alone. Every credential in it is scrubbed - see
#: `test_the_recorded_fixture_carries_no_credentials`, which is the reason this
#: file can live in a public repository at all.
RECORDED = Path(__file__).parent / "fixtures" / "screenscraper" / "jeuInfos.json"


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


def test_developer_credentials_are_not_in_this_repository() -> None:
    """The repo is public. A credential committed here is one anyone can lift
    and spend, and ScreenScraper would be right to revoke it.

    The published wheel carries them - the release workflow writes
    `_dev_credentials.py` from repository secrets and that file is git-ignored.
    This asserts the source stays clean, which is the half a reviewer cannot see
    by reading a diff six months from now.
    """
    source = Path(screenscraper.__file__).read_text(encoding="utf-8")
    assert 'DEV_ID = ""' not in source, "no literal, not even an empty one to fill in"
    assert "_dev_credentials" in source, "the injected module is how a release gets them"
    # Asked of git, not of the filesystem. The file is *supposed* to exist on a
    # developer's machine - that is the documented way to work from a clone, and
    # it is what the release workflow writes before building. What must never
    # happen is git knowing about it. The earlier version of this assertion
    # tested for absence on disk, which passed in CI, passed on a fresh clone,
    # and failed the moment somebody followed the README.
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "romgoblin/_dev_credentials.py"],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
    )
    assert tracked.returncode != 0, "a credentials file is tracked by git"


def test_a_clone_can_supply_them_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Developing against the real API should not require building a wheel."""
    monkeypatch.setattr(screenscraper, "DEV_ID", "dev")
    monkeypatch.setattr(screenscraper, "DEV_PASSWORD", "secret")
    monkeypatch.setenv("SCREENSCRAPER_SSID", "adam")
    monkeypatch.setenv("SCREENSCRAPER_SSPASSWORD", "hunter2")
    resolved = screenscraper.Credentials.resolve()
    assert (resolved.dev_id, resolved.ssid) == ("dev", "adam")


def test_the_refusal_says_which_half_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two different problems wear the same error otherwise: a clone with no
    environment, and a release built without its secrets."""
    monkeypatch.setattr(screenscraper, "DEV_ID", "")
    with pytest.raises(screenscraper.CredentialsMissing) as caught:
        screenscraper.Credentials.resolve()
    assert "SCREENSCRAPER_DEVID" in str(caught.value)


def test_a_media_url_never_carries_its_credentials_into_a_log() -> None:
    """Found while recording the fixture, and it is a property of their API
    rather than a mistake of ours: ScreenScraper authenticates its media
    endpoint through the query string, so every URL it returns looks like

        mediaJeu.php?devid=...&devpassword=...&media=box-2D

    That makes a media URL a secret rather than a link. Printing one in a
    verbose line or an error puts the developer password in somebody's terminal
    and in every log that terminal feeds.
    """
    url = (
        "https://neoclone.screenscraper.fr/api2/mediaJeu.php"
        "?devid=someone&devpassword=hunter2&ssid=member&sspassword=alsosecret"
        "&systemeid=10&media=box-2D"
    )
    safe = screenscraper.safe_url(url)
    for secret in ("someone", "hunter2", "member", "alsosecret"):
        assert secret not in safe
    # The shape survives, so a redacted URL is still recognisable in a report.
    assert "media=box-2D" in safe and "systemeid=10" in safe


def test_a_url_with_no_query_is_returned_unchanged() -> None:
    assert (
        screenscraper.safe_url("https://example.invalid/a.png") == "https://example.invalid/a.png"
    )


def test_the_recorded_fixture_carries_no_credentials() -> None:
    """The fixture is committed to a public repository. It was recorded from a
    real response, and a real response has the credentials in all 28 media
    URLs."""
    raw = RECORDED.read_text(encoding="utf-8")
    leaked = re.findall(r"(?:dev|ss)(?:id|password)=(?!REDACTED)[^&\"]+", raw)
    assert not leaked, f"credentials in a public fixture: {leaked[:3]}"


# --- the recorded response ----------------------------------------------------
#
# Recorded once, against the live service, so that the parsing above is checked
# against ScreenScraper's real shape rather than against the shape this file
# imagines. The synthetic `response()` helper agrees with whatever it is told.


def recorded() -> dict:
    return json.loads(RECORDED.read_text(encoding="utf-8"))


def test_the_cover_is_found_among_all_the_other_media() -> None:
    """The response offers 28 media for one game - screenshots, title screens,
    logos, box art from three angles, video. `box-2D` is not first and there is
    no reason it would be, so a picker that took `medias[0]` would put a
    screenshot where a cover belongs and look like it worked.
    """
    payload = recorded()
    media = payload["response"]["jeu"]["medias"]
    assert len(media) > 10, "a slimmed fixture would make this test prove nothing"
    assert media[0]["type"] != "box-2D", "the crowd is the point of this fixture"

    url = screenscraper.cover_url(payload)
    assert url is not None
    assert "media=box-2D" in url or "box-2D" in url


def test_the_real_quota_fields_parse() -> None:
    """The field names are theirs, and they are not the names anybody would
    guess: `requeststoday` and `maxrequestsperday`, lowercase and unseparated."""
    quota = screenscraper.quota_of(recorded())
    assert quota.allowed > 0, "the recorded account has a real allowance"
    assert quota.remaining <= quota.allowed


def test_the_checksum_matched_the_game() -> None:
    """The claim the whole tool rests on: a CRC32 identifies a ROM. This
    response came back from a query carrying nothing but a checksum, a filename
    and a size, and it named the right game."""
    game = recorded()["response"]["jeu"]
    names = {entry.get("text", "") for entry in game.get("noms", [])}
    assert any("Crystal" in name for name in names), names


# --- which box ----------------------------------------------------------------


def media(*entries: tuple[str, str | None]) -> dict:
    return {
        "response": {
            "jeu": {
                "medias": [
                    {"type": kind, "region": region, "url": f"https://x/?media={kind}&r={region}"}
                    for kind, region in entries
                ]
            }
        }
    }


def test_the_back_of_the_box_is_not_the_cover() -> None:
    """`box-2D-back` is the barcode and the blurb, `box-2D-side` is the spine,
    and both begin with `box-2D`. A prefix match here puts a barcode on a
    child's menu."""
    payload = media(("box-2D-back", "wor"), ("box-2D-side", "wor"), ("box-2D", "jp"))
    url = screenscraper.cover_url(payload)
    assert url is not None and "media=box-2D&" in url


def test_the_worldwide_box_wins_over_whatever_came_first() -> None:
    """The recorded response lists its German box first, for no reason visible
    from outside ScreenScraper. Without a preference an English library gets a
    German box for one game and a Japanese one for the next."""
    payload = media(("box-2D", "de"), ("box-2D", "wor"), ("box-2D", "us"))
    url = screenscraper.cover_url(payload)
    assert url is not None and "r=wor" in url


def test_an_unlisted_region_is_used_rather_than_refused() -> None:
    """Better a Brazilian box than no cover. The preference orders what exists;
    it does not filter."""
    payload = media(("box-2D", "br"))
    assert screenscraper.cover_url(payload) is not None


def test_no_box_at_all_is_none_not_a_screenshot() -> None:
    assert screenscraper.cover_url(media(("ss", "fr"), ("wheel", "de"))) is None


# --- what came back -----------------------------------------------------------


def test_bytes_that_are_not_a_png_are_refused() -> None:
    """A media URL that returns an HTML error page with a cheerful 200 is a
    thing that happens. Written to `Zelda.png` it is exactly as convincing as a
    real cover until somebody looks at the handheld."""
    assert not screenscraper.is_png(b"<html>Erreur</html>")
    assert screenscraper.is_png(b"\x89PNG\r\n\x1a\n" + b"rest")


# --- how it actually fails ----------------------------------------------------


def test_a_read_timeout_is_a_scraper_error_not_a_traceback() -> None:
    """Found on the first live run. `urlopen` wraps failures that happen while
    connecting, but a socket that goes quiet *after* the connection is
    established raises `TimeoutError` straight through - past a handler that
    only knew about `URLError`, and out of the run as a traceback. The
    per-game failure list is worth nothing if the ordinary failure walks past
    it.
    """
    client = screenscraper.Client(screenscraper.Credentials("d", "p", "", ""))

    def times_out(*args: object, **kwargs: object) -> None:
        raise TimeoutError("The read operation timed out")

    import urllib.request

    original = urllib.request.urlopen
    urllib.request.urlopen = times_out  # type: ignore[assignment]
    try:
        with pytest.raises(screenscraper.ScraperError) as caught:
            client.lookup(crc="0", filename="x.gbc", size=1)
    finally:
        urllib.request.urlopen = original  # type: ignore[assignment]
    assert "did not answer" in str(caught.value)


def test_a_reset_connection_is_a_scraper_error_too() -> None:
    client = screenscraper.Client(screenscraper.Credentials("d", "p", "", ""))

    def resets(*args: object, **kwargs: object) -> None:
        raise ConnectionResetError("Connection reset by peer")

    import urllib.request

    original = urllib.request.urlopen
    urllib.request.urlopen = resets  # type: ignore[assignment]
    try:
        with pytest.raises(screenscraper.ScraperError):
            client.lookup(crc="0", filename="x.gbc", size=1)
    finally:
        urllib.request.urlopen = original  # type: ignore[assignment]


def test_an_error_body_is_quoted_so_the_fault_can_be_placed() -> None:
    """The first live run met ScreenScraper's database being down. All it could
    say was `HTTP 500`, which sends somebody hunting for a fault in their own
    library - the answer was in the body it discarded."""
    body = (
        b"<br />\n<b>Warning</b>: mysqli_connect(): No route to host<br />\n"
        b"Erreur : Mysql a encore plante ! #mysqlbashing\n"
    )
    line = screenscraper.excerpt(body)
    assert "mysqli_connect" in line
    assert "<b>" not in line and "\n" not in line


def test_an_error_body_cannot_smuggle_a_credential_back_out() -> None:
    """The body is theirs. If it ever starts echoing the request, this is the
    last place that would notice."""
    line = screenscraper.excerpt(b"Erreur sur devid=someone&devpassword=hunter2 - reessayez")
    assert "hunter2" not in line and "someone" not in line
