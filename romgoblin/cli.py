"""The command.

Dry-run by default. `--apply` is the only thing that writes, and it writes only
files that are not there — a cover already on the card is never replaced,
whoever put it there.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from romgoblin import scan, screenscraper, systems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="romgoblin",
        description="Box art for NextUI handhelds, matched by checksum instead of filename.",
    )
    parser.add_argument("roms", type=Path, help="the Roms directory on the card, or a copy of it")
    parser.add_argument(
        "--apply", action="store_true", help="actually write. Without this, nothing changes."
    )
    parser.add_argument("--system", help="only this NextUI tag, e.g. GBC")
    parser.add_argument(
        "--allow-name-match",
        action="store_true",
        help=(
            "accept a result ScreenScraper found by filename when the checksum "
            "matched nothing. Off by default: a wrong cover looks right."
        ),
    )
    return parser


def _plan(roms: Path, tag: str | None) -> list[scan.Game]:
    games = scan.uncovered(roms)
    if tag:
        wanted = tag.upper()
        games = [game for game in games if game.tag == wanted]
    return games


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.roms.is_dir():
        print(f"error: {args.roms} is not a directory", file=sys.stderr)
        return 2

    games = _plan(args.roms, args.system)
    if not games:
        print("Every game already has a cover. Nothing to do.")
        return 0

    by_tag: dict[str, int] = {}
    for game in games:
        by_tag[game.tag] = by_tag.get(game.tag, 0) + 1
    summary = ", ".join(f"{tag} {count}" for tag, count in sorted(by_tag.items()))
    print(f"{len(games)} game(s) with no cover: {summary}")

    if not args.apply:
        for game in games[:20]:
            print(f"  would fetch  {game.tag}/{game.stem}")
        if len(games) > 20:
            print(f"  ... and {len(games) - 20} more")
        print("\nNothing was written. Re-run with --apply.")
        return 0

    try:
        client = screenscraper.Client(screenscraper.Credentials.resolve())
    except screenscraper.CredentialsMissing as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    written = 0
    unmatched: list[str] = []
    for game in games:
        try:
            payload, quota = client.lookup(
                crc=scan.crc32(game.rom),
                filename=game.rom.name,
                size=game.rom.stat().st_size,
                system_id=systems.system_id(game.tag),
            )
            url = screenscraper.cover_url(payload)
            if url is None:
                unmatched.append(f"{game.tag}/{game.stem}")
                continue
            image = client.download(url)
            game.destination.parent.mkdir(parents=True, exist_ok=True)
            game.destination.write_bytes(image)
            written += 1
            print(f"  fetched  {game.tag}/{game.stem}")
            quota.require_headroom()
        except screenscraper.QuotaExhausted as exc:
            print(f"\nStopped: {exc}")
            print(f"Fetched {written} before stopping. Run again tomorrow to continue.")
            return 0
        except screenscraper.ScraperError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    print(f"\nFetched {written} cover(s).")
    if unmatched:
        # Named rather than counted. These are the ones to look at by hand, and
        # a number tells you nothing about which.
        print(f"{len(unmatched)} not recognised by checksum:")
        for name in unmatched:
            print(f"  {name}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
