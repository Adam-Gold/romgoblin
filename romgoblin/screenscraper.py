"""The ScreenScraper client, and the quota it is obliged to respect.

Their documentation is unambiguous about whose job the quota is:

    Cette gestion de « Quota » par logiciel est désormais obligatoire afin de
    ne pas saturer nos serveurs pour rien.

So it is a requirement here with a test behind it, not a courtesy that gets
dropped when someone is in a hurry. Every response carries the caller's
allowance; the run reads it, stops cleanly when it is spent, and says where it
stopped so the next run can continue.

Requests go out one at a time. ScreenScraper grants extra concurrency by
contribution level, and assuming any would be helping yourself to someone
else's allowance.

Two credential pairs are involved and they are not interchangeable. `devid` and
`devpassword` identify *this software* and are granted to it. `ssid` and
`sspassword` identify *the person running it* and set their daily quota.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API = "https://www.screenscraper.fr/api2/jeuInfos.php"

#: Registered with ScreenScraper and reported on every request.
SOFTNAME = "romgoblin"

#: Granted to the software, not to the user — and deliberately absent from this
#: repository, which is public. A credential committed to GitHub is a credential
#: anyone can lift and spend, and secret scanners are right to flag one.
#:
#: The published wheel carries them: the release workflow writes
#: `_dev_credentials.py` from repository secrets just before building, and that
#: file is git-ignored. Developing from a clone, they come from the environment
#: instead. Either way `Credentials.resolve` refuses with the real reason rather
#: than sending a request it knows will be rejected.
try:  # pragma: no cover - present only in a built distribution
    from romgoblin._dev_credentials import DEV_ID, DEV_PASSWORD  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - the ordinary case in a clone
    DEV_ID = os.environ.get("SCREENSCRAPER_DEVID", "")
    DEV_PASSWORD = os.environ.get("SCREENSCRAPER_DEVPASSWORD", "")

TIMEOUT_SECONDS = 30


class ScraperError(Exception):
    """The service could not be reached, or did not answer in the shape asked for."""


class CredentialsMissing(ScraperError):
    """Refused before any request. Names what is absent."""


class NotAnImage(ScraperError):
    """The download did not come back a PNG. One game's problem, not the run's."""


class QuotaExhausted(ScraperError):
    """The allowance is spent. A normal end to a run, not a failure of one."""


@dataclass(frozen=True, slots=True)
class Quota:
    used: int
    allowed: int

    @property
    def remaining(self) -> int:
        return max(0, self.allowed - self.used)

    def require_headroom(self) -> None:
        if self.allowed and self.remaining <= 0:
            raise QuotaExhausted(f"daily quota spent ({self.used}/{self.allowed})")


@dataclass(frozen=True, slots=True)
class Credentials:
    dev_id: str
    dev_password: str
    ssid: str
    sspassword: str

    @classmethod
    def resolve(cls) -> Credentials:
        """Developer credentials from the package, member credentials from the
        environment — never from a config file, which is where secrets go to be
        committed by accident."""
        if not DEV_ID or not DEV_PASSWORD:
            raise CredentialsMissing(
                "No ScreenScraper developer credentials in this build. They are "
                "granted to the software rather than to you, so a release carries "
                "them; a clone needs SCREENSCRAPER_DEVID and "
                "SCREENSCRAPER_DEVPASSWORD in the environment. See the README."
            )
        return cls(
            dev_id=DEV_ID,
            dev_password=DEV_PASSWORD,
            ssid=os.environ.get("SCREENSCRAPER_SSID", ""),
            sspassword=os.environ.get("SCREENSCRAPER_SSPASSWORD", ""),
        )


def quota_of(payload: dict[str, Any]) -> Quota:
    """The caller's allowance, as the response reports it.

    Absent fields mean an anonymous or unrecognised caller, which gets a small
    allowance rather than none — reported as `allowed=0`, which
    `require_headroom` treats as "unknown, keep going" rather than "stop". The
    server is the authority either way: it starts refusing, and a refusal is
    handled where it happens.
    """
    user = (payload.get("response") or {}).get("ssuser") or {}

    def number(*names: str) -> int:
        for name in names:
            value = user.get(name)
            if value not in (None, ""):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue
        return 0

    return Quota(
        used=number("requeststoday", "requestsToday"),
        allowed=number("maxrequestsperday", "maxRequestsPerDay"),
    )


#: Preferred cover regions, best first.
#:
#: A game has box art per region and they are genuinely different pictures - a
#: European box, a Japanese box, a German box. ScreenScraper returns them in no
#: order anybody outside ScreenScraper can predict: the recorded response for
#: Pokemon Crystal offers its German box first, purely because that is how the
#: list came back.
#:
#: This is not a correctness matter - every one of them is the right game - but
#: taking whichever came first means an English-language library gets a German
#: box for one game and a Japanese one for the next, with no reason a person
#: could see. `wor` is ScreenScraper's world-wide edition and is the best answer
#: when it exists. Anything unlisted is still used, after everything listed.
REGION_PREFERENCE = ("wor", "us", "eu", "uk", "jp", "ss")

#: Not "any box". `box-2D-back` and `box-2D-side` are the back and the spine of
#: the same box, and both start with `box-2D`, so a prefix match quietly puts a
#: barcode on the menu.
COVER_TYPE = "box-2d"


def _rank(medium: dict[str, Any]) -> int:
    region = str(medium.get("region") or "").lower()
    try:
        return REGION_PREFERENCE.index(region)
    except ValueError:
        return len(REGION_PREFERENCE)


def cover_url(payload: dict[str, Any]) -> str | None:
    """The box art URL in a game response, or `None` if it carries none.

    Box art only. The recorded response offers 28 media for a single game -
    screenshots, title screens, three wheel treatments, a manual, a video, the
    box from three angles - and `box-2D` sits at index 11 of them. Taking
    whichever came first is how a tool ends up putting a screenshot where a
    cover belongs, and it looks like it worked.
    """
    game = (payload.get("response") or {}).get("jeu") or {}
    covers = [
        medium
        for medium in game.get("medias") or []
        if str(medium.get("type", "")).lower() == COVER_TYPE and medium.get("url")
    ]
    if not covers:
        return None
    return str(min(covers, key=_rank)["url"])


#: PNG's signature. NextUI reads `.media/<stem>.png`, and a file that is named
#: `.png` while being something else is the kind of failure that shows up as a
#: blank square on a handheld, days later, with nothing in any log.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def is_png(data: bytes) -> bool:
    return data.startswith(PNG_MAGIC)


@dataclass(frozen=True, slots=True)
class Client:
    credentials: Credentials

    def _get(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": SOFTNAME})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise QuotaExhausted("ScreenScraper is rate-limiting this account") from exc
            # Never the URL: it carries the credentials. The body is safe to
            # quote and is usually the only thing that says whose fault it is.
            detail = excerpt(exc.read())
            raise ScraperError(
                f"HTTP {exc.code} from ScreenScraper" + (f": {detail}" if detail else "")
            ) from exc
        except urllib.error.URLError as exc:
            raise ScraperError(f"cannot reach ScreenScraper: {exc.reason}") from exc
        except TimeoutError as exc:
            # Not a URLError. `urlopen` wraps failures that happen while
            # connecting, but a socket that goes quiet *after* the connection is
            # established raises this straight through - so the first live run
            # ended in a traceback rather than in the per-game failure list this
            # client had just been given. ScreenScraper is slow under load often
            # enough that this is the ordinary failure, not the exotic one.
            raise ScraperError(f"ScreenScraper did not answer within {TIMEOUT_SECONDS}s") from exc
        except OSError as exc:
            # A connection reset lands here for the same reason.
            raise ScraperError(f"connection to ScreenScraper failed: {exc}") from exc

    def lookup(
        self, *, crc: str, filename: str, size: int, system_id: int | None = None
    ) -> tuple[dict[str, Any], Quota]:
        """Ask which game this file is, by checksum.

        `filename` and `size` go along because ScreenScraper matches on the
        combination — but the checksum is what makes the answer an identity
        rather than a guess, and a response that matched only the name is not
        accepted by the caller.
        """
        query = {
            "devid": self.credentials.dev_id,
            "devpassword": self.credentials.dev_password,
            "softname": SOFTNAME,
            "output": "json",
            "crc": crc,
            "romnom": filename,
            "romtaille": str(size),
            "romtype": "rom",
        }
        if self.credentials.ssid:
            query["ssid"] = self.credentials.ssid
            query["sspassword"] = self.credentials.sspassword
        if system_id is not None:
            query["systemeid"] = str(system_id)

        raw = self._get(f"{API}?{urllib.parse.urlencode(query)}")
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise ScraperError(f"ScreenScraper did not return JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ScraperError("ScreenScraper returned something that is not an object")
        return payload, quota_of(payload)

    def download(self, url: str) -> bytes:
        """The image behind a media URL, as PNG, or a refusal.

        Two things are asked of the response and neither is assumed. `mediaformat`
        asks ScreenScraper to hand back a PNG - their media endpoint accepts the
        conversion, and an endpoint that did not would ignore an unknown
        parameter rather than fail. Then the bytes are checked, because what was
        asked for and what arrived are different facts.

        A media URL that returns an HTML error page with a cheerful 200 is a
        thing that happens, and writing that to `Zelda.png` would leave a file
        that is exactly as convincing as a real one until somebody looks at the
        handheld.
        """
        separator = "&" if "?" in url else "?"
        data = self._get(f"{url}{separator}mediaformat=png")
        if not is_png(data):
            # Never the URL - it carries the credentials. The body is quoted,
            # because when their database is down the media endpoint serves the
            # same French error page as this, with a cheerful 200, and 513 bytes
            # of unexplained not-a-PNG is not something anybody can act on.
            raise NotAnImage(
                f"not a PNG ({len(data)} bytes): {excerpt(data, 100)}"
                if data
                else "ScreenScraper returned an empty response"
            )
        return data


#: ScreenScraper returns media URLs with the caller's credentials embedded in the
#: query string - `mediaJeu.php?devid=...&devpassword=...`. That is how their
#: media endpoint authenticates, and it makes a media URL a secret rather than a
#: link.
#:
#: The consequence is not theoretical: printing one in a verbose line, an error
#: message or a crash report puts the developer password in somebody's terminal
#: and in every log that terminal feeds. Anything that shows a URL to a human or
#: writes one to disk goes through this first.
SENSITIVE_PARAMS = frozenset({"devid", "devpassword", "ssid", "sspassword", "devdebugpassword"})


def excerpt(data: bytes, limit: int = 140) -> str:
    """One readable line from a response body, for saying what went wrong.

    ScreenScraper answers a failure with a page rather than a code, and the page
    is the only thing that distinguishes "your ROM is unknown" from "our
    database is down". The first live run of this tool met the second and could
    only report `HTTP 500`, which sends somebody looking for a fault in their
    own library:

        Warning: mysqli_connect(): No route to host ...
        Nous rencontrons actuellement des problemes mySQL.

    Markup and blank lines are dropped, and anything shaped like a credential is
    redacted on the way out - the body is theirs and this is the last place that
    would notice if it started echoing a request back.
    """
    text = re.sub(r"<[^>]+>", " ", data.decode("utf-8", errors="replace"))
    text = re.sub(r"(?i)\b(dev|ss)(id|password)=\S+", r"\1\2=REDACTED", text)
    text = " ".join(text.split())
    return text[:limit] + ("..." if len(text) > limit else "")


def safe_url(url: str) -> str:
    """The same URL with every credential replaced, for showing or logging."""
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    clean = [(k, "REDACTED" if k in SENSITIVE_PARAMS else v) for k, v in query]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(clean)))
