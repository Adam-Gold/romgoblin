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
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

API = "https://www.screenscraper.fr/api2/jeuInfos.php"

#: Registered with ScreenScraper and reported on every request.
SOFTNAME = "romgoblin"

#: Granted to the software, not to the user. Empty until ScreenScraper issues
#: them; `Credentials.resolve` refuses rather than sending a request that would
#: be rejected, so the failure names the real reason.
DEV_ID = ""
DEV_PASSWORD = ""

TIMEOUT_SECONDS = 30


class ScraperError(Exception):
    """The service could not be reached, or did not answer in the shape asked for."""


class CredentialsMissing(ScraperError):
    """Refused before any request. Names what is absent."""


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
                "This build has no ScreenScraper developer credentials. "
                "They are granted to the software, not to you: see the README."
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


def cover_url(payload: dict[str, Any]) -> str | None:
    """The box art URL in a game response, or `None` if it carries none.

    Box art only. A response also offers screenshots, title screens, logos and
    video, and taking whichever happens to come first is how a tool ends up
    putting a screenshot where a cover belongs.
    """
    game = (payload.get("response") or {}).get("jeu") or {}
    for medium in game.get("medias") or []:
        if medium.get("type") in ("box-2D", "box-2d") and medium.get("url"):
            return str(medium["url"])
    return None


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
            raise ScraperError(f"HTTP {exc.code} from ScreenScraper") from exc
        except urllib.error.URLError as exc:
            raise ScraperError(f"cannot reach ScreenScraper: {exc.reason}") from exc

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
        return self._get(url)
