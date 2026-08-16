"""Finding the games, and computing the fingerprint that identifies each one.

A ROM directory is walked one system folder at a time. Everything hidden is
skipped — `.media` is where the covers go, and macOS scatters `._` sidecars
across any card it touches — and so is anything that already has a cover,
because this tool never replaces one.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from romgoblin import systems

#: Read in chunks so a 700 MB disc image does not become 700 MB of memory.
_CHUNK = 1 << 20

#: Files that sit beside ROMs and are not games. A cue sheet describes a disc
#: whose `.bin` is the game; a `.sbi` is subchannel data belonging to an image
#: already counted. Asking ScreenScraper about either wastes a request from a
#: quota the user is obliged to respect.
COMPANION_SUFFIXES = frozenset({".cue", ".sbi", ".m3u", ".txt", ".xml", ".dat"})


@dataclass(frozen=True, slots=True)
class Game:
    """One game with no cover, and the fingerprint that identifies it."""

    rom: Path
    system_folder: Path
    tag: str
    destination: Path

    @property
    def stem(self) -> str:
        return self.rom.stem


def crc32(path: Path) -> str:
    """The checksum ScreenScraper matches on, in the form it expects.

    Eight uppercase hex digits, zero-padded. A bare `f"{n:X}"` drops leading
    zeros and the API compares the string, so a checksum beginning with a zero
    would silently never match.
    """
    checksum = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            checksum = zlib.crc32(chunk, checksum)
    return f"{checksum:08X}"


def system_folders(roms_root: Path) -> Iterator[tuple[Path, str]]:
    """Every folder under `roms_root` that carries a NextUI system tag."""
    if not roms_root.is_dir():
        return
    for folder in sorted(roms_root.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        tag = systems.tag_of(folder)
        if tag is not None:
            yield folder, tag


def _is_game(path: Path) -> bool:
    if not path.is_file() or path.name.startswith("."):
        return False
    return path.suffix.lower() not in COMPANION_SUFFIXES


def uncovered(roms_root: Path) -> list[Game]:
    """Games that have no cover yet.

    Games already carrying one are not returned at all — not skipped later,
    not fetched and discarded. Whoever wrote that image, this tool leaves it
    alone, which is what lets it run beside the scraper on the device.
    """
    found: list[Game] = []
    for folder, tag in system_folders(roms_root):
        for rom in sorted(folder.iterdir()):
            if not _is_game(rom):
                continue
            destination = systems.image_for(folder, rom)
            if destination.exists():
                continue
            found.append(Game(rom=rom, system_folder=folder, tag=tag, destination=destination))
    return found
