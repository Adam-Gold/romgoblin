# ROMgoblin 👺

*A small goblin that runs through your ROM library and fetches the box art.*

For [NextUI](https://github.com/LoveRetro/NextUI) handhelds. Matched by **checksum**, not by filename.

## Why this exists

NextUI gets its artwork from a scraper that runs **on the device**. That works, but it means every batch of new games costs you a round trip: eject the card, put it in the handheld, run the scraper, bring it back. The library lives on your computer; the artwork does not.

There are already two good desktop scrapers for NextUI. Both match games **by filename**, against the Libretro thumbnail archive. That is fast and needs no account, and for most libraries it is fine.

It is not fine for the cases that matter:

- `Crash Bandicoot` is a PlayStation game. `Crash Bandicoot` is also a *different* Game Boy Advance game. A filename cannot tell you which one you have.
- `Disney's Hercules Action Game (Rerelease).chd` matches no official title at all.
- A hack, a translation, or a bad dump carries the name of the game it was made from, and none of its content.

**A wrong cover is worse than no cover, because it looks right.** You do not find out until a five-year-old picks the wrong game.

ROMgoblin asks a different question. It computes the CRC32 of each ROM and asks [ScreenScraper.fr](https://www.screenscraper.fr) which game *that file* is. A checksum is identity; a filename is a guess.

## What it does

- Walks a ROM directory, one system at a time.
- Identifies each game by CRC32, file size and filename — the combination ScreenScraper matches on.
- Downloads the box art and writes it where NextUI looks: `.media/<stem>.png` inside the system folder, so `Zelda.zip` gets `Zelda.png`.
- **Never overwrites and never deletes.** A cover that is already there is left alone, whoever put it there. You can run this alongside the on-device scraper without either one destroying the other's work.
- Stops cleanly when your ScreenScraper quota runs out, and picks up where it left off next time.

## What it does not do

- **It does not guess.** A ROM whose checksum ScreenScraper does not recognise gets no artwork and is reported by name, so you know what to look at. Name-based matching is available behind an explicit flag and is never the default.
- **One source.** ScreenScraper only. No fallback chain, no merging.
- **Box art only.** Not screenshots, not titles, not logos, not videos, not manuals.
- **NextUI only.** The whole value here is writing exactly the layout NextUI reads. If you need muOS or Onion or EmulationStation, other tools do that well.

## Install

```bash
pipx install romgoblin
```

## Usage

```bash
romgoblin /Volumes/NEXTUI/Roms
```

Dry-run by default — it tells you what it would fetch and stops. Nothing is written until you say so:

```bash
romgoblin /Volumes/NEXTUI/Roms --apply
```

## Credentials

ScreenScraper needs two pairs. The **developer** pair identifies this software and ships with it. The **member** pair is yours, and it sets your daily quota:

```bash
export SCREENSCRAPER_SSID=your-username
export SCREENSCRAPER_SSPASSWORD=your-password
```

An account is free. Without one you get the anonymous allowance, which is small.

Credentials are read from the environment and never from a config file.

## Licence

MIT.
