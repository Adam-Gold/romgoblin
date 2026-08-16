<div align="center">

<img src="https://pub-fb8f91556fc24a1da5991428b147e590.r2.dev/romgoblin.png" alt="ROMgoblin" width="380">

[![Tests](https://img.shields.io/github/actions/workflow/status/Adam-Gold/romgoblin/tests.yml?branch=main&label=tests&style=flat-square)](https://github.com/Adam-Gold/romgoblin/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://www.python.org/downloads/)
[![Licence](https://img.shields.io/github/license/Adam-Gold/romgoblin?style=flat-square)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen?style=flat-square)](pyproject.toml)

**Box art for [NextUI](https://github.com/LoveRetro/NextUI) handhelds, fetched from your computer.**

*Finds the art. Never guesses.*

</div>

---

```console
$ romgoblin /Volumes/NextUI/Roms
5 game(s) with no cover: MGBA 2, N64 2, PS 1
  would fetch  MGBA/Rayman 3
  would fetch  MGBA/Wario Land 4
  would fetch  N64/Mario Kart 64
  would fetch  N64/Pokemon Snap
  would fetch  PS/Spyro 2 - Ripto's Rage!

Nothing was written. Re-run with --apply.
```

Dry-run by default. Games that already have a cover are not listed, because they are never touched.

## Why this exists

NextUI gets its artwork from a scraper that runs **on the device**. That works, but it means every batch of new games costs a round trip: eject the card, put it in the handheld, run the scraper, bring it back. The library lives on your computer; the artwork does not.

There are already good desktop scrapers for NextUI. They match games **by filename**, against the Libretro thumbnail archive. That is fast, needs no account, and for most libraries it is fine.

It is not fine for the cases that matter:

- `Crash Bandicoot` is a PlayStation game. `Crash Bandicoot` is also a *different* Game Boy Advance game. A filename cannot tell you which one you have.
- `Disney's Hercules Action Game (Rerelease).chd` matches no official title at all.
- A hack, a translation, or a bad dump carries the name of the game it was made from, and none of its content.

**A wrong cover is worse than no cover, because it looks right.** You do not find out until someone picks the wrong game.

ROMgoblin asks a different question. It computes the CRC32 of each ROM and asks [ScreenScraper.fr](https://www.screenscraper.fr) which game *that file* is. A checksum is identity; a filename is a guess.

## Installation

| | |
| --- | --- |
| **pipx** *(recommended)* | `pipx install romgoblin` |
| **uv** | `uv tool install romgoblin` |
| **pip** | `pip install romgoblin` |
| **From source** | `git clone https://github.com/Adam-Gold/romgoblin && cd romgoblin && pip install -e .` |

Python 3.11 or newer. No dependencies — the standard library computes the checksum and makes the request.

## Usage

```console
$ romgoblin <path to your Roms directory>
```

Point it at the `Roms` folder on the card, or at a copy of it on disk. It walks each system folder, finds the games with no cover, and tells you what it would fetch.

Nothing is written until you say so:

```console
$ romgoblin /Volumes/NextUI/Roms --apply
```

| Flag | |
| --- | --- |
| `--apply` | actually write. Without it, nothing changes. |
| `--system TAG` | only one system, e.g. `--system N64` |
| `--allow-name-match` | accept a result found by filename when the checksum matched nothing. Off by default. |

Covers are written to `.media/<stem>.png` inside each system folder, which is where NextUI looks — so `Zelda.zip` gets `Zelda.png`.

## What it will not do

**It will not guess.** A ROM whose checksum ScreenScraper does not recognise gets no artwork, and is reported by name so you know what to look at. Name matching exists behind `--allow-name-match` and is never the default.

**It will not overwrite, and it will not delete.** A cover that is already there is left alone, whoever put it there. Run it beside the on-device scraper and neither destroys the other's work.

**It will not take whatever image comes first.** Box art only — not screenshots, not title screens, not logos.

**It will not exhaust your quota.** ScreenScraper reports your remaining allowance on every response; when it runs out the tool stops cleanly, says where it stopped, and continues from there next time.

**One source, one target.** ScreenScraper only, NextUI only. If you need Libretro thumbnails, muOS or EmulationStation, other tools do that well and this one does not try.

## Credentials

ScreenScraper needs two pairs, and they are not interchangeable.

The **developer** pair identifies this software and ships with it.

The **member** pair is yours, and it sets your daily quota:

```bash
export SCREENSCRAPER_SSID=your-username
export SCREENSCRAPER_SSPASSWORD=your-password
```

An account is free. Without one you get the anonymous allowance, which is small but real.

Credentials are read from the environment and never from a configuration file.

## Licence

MIT. The artwork it downloads is not ours and is not redistributed — it goes from ScreenScraper to your SD card and nowhere else.
