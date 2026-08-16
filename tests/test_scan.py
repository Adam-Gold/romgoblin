"""Finding games, and the fingerprint that identifies one."""

from __future__ import annotations

import zlib
from pathlib import Path

from romgoblin import scan, systems


def card(tmp_path: Path) -> Path:
    roms = tmp_path / "Roms"
    (roms / "Game Boy Color (GBC)").mkdir(parents=True)
    return roms


def test_a_system_folder_is_recognised_by_its_tag(tmp_path: Path) -> None:
    roms = card(tmp_path)
    (roms / "Not A System").mkdir()
    assert [tag for _, tag in scan.system_folders(roms)] == ["GBC"]


def test_a_game_with_no_cover_is_found(tmp_path: Path) -> None:
    roms = card(tmp_path)
    (roms / "Game Boy Color (GBC)" / "Zelda.gbc").write_bytes(b"rom")
    found = scan.uncovered(roms)
    assert [game.stem for game in found] == ["Zelda"]
    assert found[0].destination.name == "Zelda.png"


def test_a_game_that_already_has_one_is_left_entirely_alone(tmp_path: Path) -> None:
    """Not skipped later — never returned. Whoever wrote that image, including
    the scraper on the device, this tool does not touch it."""
    roms = card(tmp_path)
    folder = roms / "Game Boy Color (GBC)"
    (folder / "Zelda.gbc").write_bytes(b"rom")
    media = folder / systems.MEDIA_DIR
    media.mkdir()
    (media / "Zelda.png").write_bytes(b"png")
    assert scan.uncovered(roms) == []


def test_artwork_is_named_after_the_stem(tmp_path: Path) -> None:
    """`Zelda.zip` takes `Zelda.png`. NextUI names a save after the full
    filename and artwork after the stem, and getting the two the wrong way
    round is a silent miss rather than an error."""
    roms = card(tmp_path)
    (roms / "Game Boy Color (GBC)" / "Zelda.zip").write_bytes(b"rom")
    assert scan.uncovered(roms)[0].destination.name == "Zelda.png"


def test_companions_and_hidden_files_are_not_games(tmp_path: Path) -> None:
    """A cue sheet describes a disc whose bin is the game. Asking about it
    spends a request from a quota the user is obliged to respect."""
    roms = card(tmp_path)
    folder = roms / "Game Boy Color (GBC)"
    for name in ("Zelda.cue", "Zelda.sbi", "._Zelda.gbc", "map.txt"):
        (folder / name).write_bytes(b"x")
    (folder / "Zelda.bin").write_bytes(b"rom")
    assert [game.rom.name for game in scan.uncovered(roms)] == ["Zelda.bin"]


def test_crc32_is_eight_uppercase_hex_digits(tmp_path: Path) -> None:
    rom = tmp_path / "Game.gbc"
    rom.write_bytes(b"contents")
    assert scan.crc32(rom) == f"{zlib.crc32(b'contents'):08X}"


def test_a_leading_zero_survives(tmp_path: Path) -> None:
    """`f"{n:X}"` would drop it, and ScreenScraper compares the string."""
    rom = tmp_path / "Game.gbc"
    for candidate in (b"a", b"b", b"c", b"d", b"e", b"f", b"g", b"h"):
        rom.write_bytes(candidate)
        assert len(scan.crc32(rom)) == 8
