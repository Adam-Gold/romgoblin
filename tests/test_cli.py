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
