"""The command's default: it does not write."""

from __future__ import annotations

from pathlib import Path

from romgoblin import cli


def card(tmp_path: Path) -> Path:
    roms = tmp_path / "Roms"
    folder = roms / "Game Boy Color (GBC)"
    folder.mkdir(parents=True)
    (folder / "Zelda.gbc").write_bytes(b"rom")
    return roms


def test_a_missing_directory_is_a_usage_error(tmp_path: Path) -> None:
    assert cli.main([str(tmp_path / "nowhere")]) == 2


def test_the_default_writes_nothing(tmp_path: Path, capsys) -> None:
    roms = card(tmp_path)
    assert cli.main([str(roms)]) == 0
    assert "Nothing was written" in capsys.readouterr().out
    assert not (roms / "Game Boy Color (GBC)" / ".media").exists()


def test_apply_without_credentials_refuses_before_touching_anything(tmp_path: Path, capsys) -> None:
    """Exit 2: this is a configuration problem, not a transient one. Nothing is
    created on the way to finding out."""
    roms = card(tmp_path)
    assert cli.main([str(roms), "--apply"]) == 2
    assert not (roms / "Game Boy Color (GBC)" / ".media").exists()


def test_system_narrows_the_plan(tmp_path: Path, capsys) -> None:
    roms = card(tmp_path)
    other = roms / "Sega Genesis (MD)"
    other.mkdir()
    (other / "Sonic.md").write_bytes(b"rom")

    cli.main([str(roms), "--system", "gbc"])
    out = capsys.readouterr().out
    assert "Zelda" in out
    assert "Sonic" not in out


def test_a_card_with_every_cover_present_says_so(tmp_path: Path, capsys) -> None:
    roms = tmp_path / "Roms"
    (roms / "Game Boy Color (GBC)").mkdir(parents=True)
    assert cli.main([str(roms)]) == 0
    assert "Nothing to do" in capsys.readouterr().out


# --- the run that goes wrong in the middle ------------------------------------
#
# The interesting path, and the one no dry run reaches. A real library is
# around a hundred games, so "what happens when number 40 fails" is not an edge
# case - it is Tuesday.


PNG = b"\x89PNG\r\n\x1a\n" + b"pretend"


class FakeClient:
    """Stands in for ScreenScraper. Answers by ROM name so a test can say which
    game misbehaves."""

    def __init__(self, behaviour: dict[str, str]) -> None:
        self.behaviour = behaviour
        self.downloads = 0

    def lookup(self, *, crc, filename, size, system_id):  # noqa: ANN001, ANN003
        from romgoblin import screenscraper

        what = self.behaviour.get(Path(filename).stem, "ok")
        if what == "lookup-fails":
            raise screenscraper.ScraperError("HTTP 503 from ScreenScraper")
        if what == "quota":
            raise screenscraper.QuotaExhausted("daily quota spent (100/100)")
        medias = (
            []
            if what == "no-cover"
            else [{"type": "box-2D", "region": "wor", "url": "https://x/?m=1"}]
        )
        payload = {"response": {"ssuser": {}, "jeu": {"medias": medias}}}
        return payload, screenscraper.Quota(used=1, allowed=100)

    def download(self, url: str) -> bytes:  # noqa: ARG002
        self.downloads += 1
        return PNG


def library(tmp_path: Path, *names: str) -> Path:
    roms = tmp_path / "Roms"
    folder = roms / "Game Boy Color (GBC)"
    folder.mkdir(parents=True)
    for name in names:
        (folder / f"{name}.gbc").write_bytes(b"rom-" + name.encode())
    return roms


def run(monkeypatch, roms: Path, client: FakeClient) -> int:
    from romgoblin import screenscraper

    monkeypatch.setattr(
        screenscraper.Credentials,
        "resolve",
        classmethod(lambda cls: screenscraper.Credentials("d", "p", "s", "p")),
    )
    monkeypatch.setattr(screenscraper, "Client", lambda credentials: client)
    return cli.main([str(roms), "--apply"])


def test_one_failure_does_not_cost_the_rest_of_the_run(tmp_path: Path, monkeypatch, capsys) -> None:
    """A timeout on game two used to end the run, abandoning games three and
    four - and every request already made was spent out of the day's
    allowance."""
    roms = library(tmp_path, "One", "Two", "Three", "Four")
    client = FakeClient({"Two": "lookup-fails"})
    assert run(monkeypatch, roms, client) == 0

    media = roms / "Game Boy Color (GBC)" / ".media"
    assert sorted(p.name for p in media.iterdir()) == ["Four.png", "One.png", "Three.png"]
    out = capsys.readouterr().out
    assert "1 failed and can be retried" in out
    assert "Two" in out


def test_a_failure_and_an_unrecognised_rom_are_reported_apart(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Different problems, different answers: a checksum nobody knows is a ROM
    to look at by hand, a 503 is worth running again in a minute."""
    roms = library(tmp_path, "Known", "Unknown", "Flaky")
    run(monkeypatch, roms, FakeClient({"Unknown": "no-cover", "Flaky": "lookup-fails"}))
    out = capsys.readouterr().out
    assert "not recognised by checksum" in out and "failed and can be retried" in out


def test_a_spent_quota_stops_and_says_where_it_got_to(tmp_path: Path, monkeypatch, capsys) -> None:
    """Exit zero. The allowance ran out, which is the arrangement working, not
    the tool failing."""
    roms = library(tmp_path, "A", "B", "C")
    assert run(monkeypatch, roms, FakeClient({"B": "quota"})) == 0
    out = capsys.readouterr().out
    assert "Run again tomorrow to continue" in out
    # Whatever it managed is kept. The next run finds it and skips it.
    assert (roms / "Game Boy Color (GBC)" / ".media" / "A.png").exists()


def test_a_cover_that_is_already_there_is_never_fetched_again(tmp_path: Path, monkeypatch) -> None:
    """The promise the README makes about running beside the on-device scraper:
    it costs no request, so it cannot cost the quota either."""
    roms = library(tmp_path, "Have", "Need")
    media = roms / "Game Boy Color (GBC)" / ".media"
    media.mkdir()
    (media / "Have.png").write_bytes(b"someone else's cover")

    client = FakeClient({})
    run(monkeypatch, roms, client)
    assert client.downloads == 1
    assert (media / "Have.png").read_bytes() == b"someone else's cover"
