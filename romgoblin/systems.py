"""NextUI's folder convention, and the mapping to ScreenScraper's system numbers.

NextUI identifies a system by a bracketed tag at the end of the folder name:
`Roms/Game Boy Color (GBC)/`. The words before the tag are cosmetic and a card
may spell them however its owner likes, so the tag is the only part that can be
read as data.

The `systemeid` mapping below is an **accuracy refinement, not a requirement**.
ScreenScraper can answer a checksum query without being told the system, and
for a CRC32 that it recognises the answer is the same either way. Supplying the
system narrows the search and rules out a checksum collision across consoles,
which is why it is worth having — but a tag missing from this table costs
precision, not function.

Every value here has to come from ScreenScraper's own `systemesListe.php`.
None may be guessed: a wrong number returns artwork for a different console,
and artwork that is confidently wrong is the failure this tool exists to avoid.
"""

from __future__ import annotations

import re
from pathlib import Path

#: `Any Name You Like (TAG)` — the tag is uppercase letters and digits, and it
#: is the last thing in the folder name.
TAG_RE = re.compile(r"\(([A-Z0-9]+)\)\s*$")

#: NextUI keeps a system's artwork in a hidden folder inside the system folder.
MEDIA_DIR = ".media"

#: One image per game, named after the ROM's stem: `Zelda.zip` -> `Zelda.png`.
IMAGE_SUFFIX = ".png"

#: NextUI tag -> ScreenScraper `systemeid`.
#:
#: Deliberately empty until the values are read from ScreenScraper's own
#: `systemesListe.php` with granted credentials. `tests/test_systems.py`
#: asserts that whatever is here is a plausible tag mapped to a positive
#: integer; it cannot assert the number is *correct*, which is exactly why
#: guessing is forbidden rather than merely discouraged.
SYSTEM_IDS: dict[str, int] = {}


def tag_of(folder: Path) -> str | None:
    """The system tag of a ROM folder, or `None` if it does not carry one.

    A folder without a tag is not a system folder. NextUI will not scan it
    either, so skipping it is agreement with the device rather than a
    limitation of this tool.
    """
    found = TAG_RE.search(folder.name)
    return found.group(1) if found else None


def system_id(tag: str) -> int | None:
    """ScreenScraper's number for this system, if it is known.

    `None` means "ask without narrowing", not "give up".
    """
    return SYSTEM_IDS.get(tag.upper())


def media_dir(system_folder: Path) -> Path:
    return system_folder / MEDIA_DIR


def image_for(system_folder: Path, rom: Path) -> Path:
    """Where this ROM's cover belongs.

    By stem, not by full filename. `Zelda.zip` takes `Zelda.png`, which is the
    convention NextUI reads and the opposite of how it names a save file.
    """
    return media_dir(system_folder) / f"{rom.stem}{IMAGE_SUFFIX}"
