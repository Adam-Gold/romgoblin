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
    parser.add_argument(
        "--max-width",
        type=int,
        default=screenscraper.DEFAULT_MAX_WIDTH,
        metavar="PX",
        help=(
            f"resize covers to this width before download (default "
            f"{screenscraper.DEFAULT_MAX_WIDTH}, 0 for whatever ScreenScraper has). "
            "Their side does the resizing, so a smaller number is bandwidth and "
            "card space never spent rather than spent and thrown away."
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

    # ScreenScraper goes down. The first live run of this tool met their
    # database being unreachable, and worked exactly as designed: fourteen
    # games, fourteen identical failures, seven of them after a thirty-second
    # wait. That is three minutes to learn one fact, printed fourteen times.
    #
    # So a run that has achieved nothing and failed this many times in a row
    # stops and says the one thing that is true. The counter resets on any
    # success, because a library with a few unreachable games is a different
    # situation and must not be cut short.
    GIVE_UP_AFTER = 3

    written = 0
    in_a_row = 0
    # Kept apart because they are different problems with different answers. A
    # checksum nobody recognises is a ROM to look at by hand; a request that
    # failed is worth running again in a minute. Merging them into one
    # "skipped" count would send somebody hunting for a bad dump that was a
    # timeout.
    unmatched: list[str] = []
    failed: list[str] = []

    for game in games:
        name = f"{game.tag}/{game.stem}"
        try:
            payload, quota = client.lookup(
                crc=scan.crc32(game.rom),
                filename=game.rom.name,
                size=game.rom.stat().st_size,
                system_id=systems.system_id(game.tag),
            )
        except screenscraper.QuotaExhausted as exc:
            return _stopped(exc, written, unmatched, failed)
        except screenscraper.ScraperError as exc:
            # One game's failure is not the run's. Stopping here would mean a
            # single timeout at game 40 of 107 costs the other 67, and every
            # one of those is a request already paid for out of the day's
            # allowance.
            failed.append(f"{name}: {exc}")
            in_a_row += 1
            if written == 0 and in_a_row >= GIVE_UP_AFTER:
                return _gave_up(failed)
            continue

        url = screenscraper.cover_url(payload)
        if url is None:
            # Not a failure. Their service answered; it does not know this ROM.
            in_a_row = 0
            unmatched.append(name)
            continue

        try:
            image = client.download(url, max_width=args.max_width)
        except screenscraper.QuotaExhausted as exc:
            return _stopped(exc, written, unmatched, failed)
        except screenscraper.ScraperError as exc:
            failed.append(f"{name}: {exc}")
            in_a_row += 1
            if written == 0 and in_a_row >= GIVE_UP_AFTER:
                return _gave_up(failed)
            continue

        # Written last, and only once there are verified PNG bytes in hand. A
        # partially written cover is a file NextUI will happily show as a
        # broken square.
        game.destination.parent.mkdir(parents=True, exist_ok=True)
        game.destination.write_bytes(image)
        written += 1
        in_a_row = 0
        print(f"  fetched  {name}")

        try:
            quota.require_headroom()
        except screenscraper.QuotaExhausted as exc:
            return _stopped(exc, written, unmatched, failed)

    print(f"\nFetched {written} cover(s).")
    _report(unmatched, failed)
    return 0


def _gave_up(failed: list[str]) -> int:
    """Stopped early, having achieved nothing and failed the same way each time.

    Exit 1, unlike a spent quota: the allowance running out is the arrangement
    working, and this is the service being unavailable. A script that runs this
    nightly should be able to tell those apart.
    """
    print(f"\nStopped after {len(failed)} failures in a row, having fetched nothing.")
    print("This looks like ScreenScraper rather than your library. What it said:")
    print(f"  {failed[-1].split(': ', 1)[-1]}")
    print("\nNothing was written. Try again later.")
    return 1


def _report(unmatched: list[str], failed: list[str]) -> None:
    """Named rather than counted. These are the ones to look at, and a number
    tells you nothing about which."""
    if unmatched:
        print(f"{len(unmatched)} not recognised by checksum:")
        for name in unmatched:
            print(f"  {name}")
    if failed:
        print(f"{len(failed)} failed and can be retried:")
        for name in failed:
            print(f"  {name}")


def _stopped(exc: Exception, written: int, unmatched: list[str], failed: list[str]) -> int:
    """A spent quota ends the run cleanly. It is where the run got to, not a
    failure of it - so it says so, reports what it found, and exits zero."""
    print(f"\nStopped: {exc}")
    print(f"Fetched {written} before stopping. Run again tomorrow to continue.")
    _report(unmatched, failed)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
