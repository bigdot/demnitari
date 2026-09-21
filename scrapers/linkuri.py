"""Links (website + social networks), in one place — parsed, not guessed.

  - normalizeaza_url(text): a real http(s) URL with a real hostname (labels +
    TLD), or None. "camera-deputaţilor/alin-colesa" is not a URL.
  - is_reachable(url): live check — does the site answer? Run once per website
    at the end of the build; an unreachable site is not published.
  - clasifica(url): the network the HOST belongs to ("facebook", "youtube"...)
    or "site". By host, not by substring.
  - normalizeaza(contacts): over a contacts block — invalid URLs dropped, a
    "website" that is really a social profile moved to `socials`, each social
    filed under the network of its host, deduplicated.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

import requests

from scrapers.fetch import UA

log = logging.getLogger("demnitari.linkuri")

_RETELE = {
    "facebook.com": "facebook", "fb.com": "facebook", "fb.me": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "youtube.com": "youtube", "youtu.be": "youtube",
    "tiktok.com": "tiktok",
    "x.com": "x", "twitter.com": "x",
}

_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST_RE = re.compile(rf"(?:{_LABEL}\.)+[a-z]{{2,}}")


# un URL scris in text liber: cu protocol, cu www., sau domeniu gol pe un TLD uzual
_IN_TEXT_RE = re.compile(
    r"(?<![\w@.-])(?:https?://|www\.)[^\s<>\"'()\[\]]+"
    r"|(?<![\w@.-])(?:[a-z0-9-]+\.)+(?:ro|com|eu|org|net|md|info)\b(?:/[^\s<>\"'()\[\]]*)?",
    re.I)


def pozitii(text: str) -> list[tuple[int, int, str]]:
    """(start, end, URL as written) for every valid URL written in `text`."""
    out = []
    for m in _IN_TEXT_RE.finditer(text or ""):
        brut = m.group(0).rstrip(".,;:")
        if normalizeaza_url(brut):
            out.append((m.start(), m.start() + len(brut), brut))
    return out


def normalizeaza_url(text: str) -> str | None:
    if not isinstance(text, str) or not text.strip() or " " in text.strip():
        return None
    url = text.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or "@" in p.netloc or not _HOST_RE.fullmatch(host):
        return None
    return url


def is_reachable(url: str, timeout: int = 10, incercari: int = 2) -> bool:
    """Reachability check: one GET (redirects followed), retried once.

    Alive = the server gave a page (< 400) or refused US specifically (401/403/
    429: a WAF that blocks bots still serves browsers). Dead = DNS failure,
    connection refused, timeout, broken TLS, 404/410, 5xx.
    """
    eroare = None
    for _ in range(incercari):
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": UA},
                             allow_redirects=True, stream=True)
            r.close()
            if r.status_code < 400 or r.status_code in (401, 403, 429):
                log.debug("site %s -> %d", url, r.status_code)
                return True
            eroare = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            eroare = type(e).__name__
    log.warning("site unreachable (%s): %s", eroare, url)
    return False


def clasifica(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for domeniu, retea in _RETELE.items():
        if host == domeniu or host.endswith("." + domeniu):
            return retea
    return "site"


def normalizeaza(contacts: dict, cine: str = "") -> None:
    """Fix `website` / `socials` of a member's contacts, in place."""
    candidati = [(None, contacts.get("website"))]  # (eticheta din socials, valoare)
    for s in contacts.get("socials") or []:
        if isinstance(s, dict):
            candidati.extend(s.items())

    website, socials, vazute = None, [], set()
    for eticheta, brut in candidati:
        if not brut:
            continue
        url = normalizeaza_url(brut)
        if url is None:
            log.warning("link invalid, scos: %r (%s)", brut, cine)
            continue
        cheie = url.split("://", 1)[1].removeprefix("www.").rstrip("/").lower()
        if cheie in vazute:
            continue
        vazute.add(cheie)
        retea = clasifica(url)
        if retea != "site":
            socials.append({retea: url})
        elif eticheta:  # retea pe care n-o stim dupa host (ex: telegram) — ramane
            socials.append({eticheta: url})
        else:
            website = url
    contacts["website"] = website
    contacts["socials"] = socials
