"""Email addresses, in one place — same idea as telefoane.py.

  - gaseste(text): addresses found in free text (mechanical extraction).
  - valideaza(email, uid): what an address IS for that member, decided BEFORE it
    is put in any field:
        "oficial"  the member's own chamber domain — a deputy (uid "2:…") only
                   @cdep.ro, a senator (uid "1:…") only @senat.ro;
        "altul"    any other well-formed, non-parliament address;
        None       not admitted: malformed, or a parliament address of the other
                   chamber (a past mandate's mailbox, closed when it ended).
  - admite(candidati, uid): builds (official_email, other_emails) out of
    candidate addresses, through valideaza. Used by the scrape when it assembles
    a member and on whatever the LLM proposes.

The pattern is the usual practical subset of RFC 5322: the local part is
letters/digits and `._%+-` (no `/`, no `:` — a URL is not an email), the domain
is made of RFC 1035 labels (the HTML5/WHATWG definition) and ends in a TLD.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger("demnitari.emailuri")

# camera din uid ("<cam>:<idm>"): 2 = deputat, 1 = senator
DOMENIU_CAMERA = {"2": "cdep.ro", "1": "senat.ro"}

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL = rf"[A-Za-z0-9._%+-]+@(?:{_LABEL}\.)+[A-Za-z]{{2,}}"
# \w in the look-arounds: an address glued to a non-ASCII word ("Bucureşti.x@gov.ro")
# is skipped whole, not cut in the middle of the word
_IN_TEXT_RE = re.compile(rf"(?<![\w.%+/-]){_EMAIL}(?![\w-])")
_INTREG_RE = re.compile(_EMAIL)


def pozitii(text: str) -> list[tuple[int, int, str]]:
    """(start, end, address) for every email address written in `text`."""
    return [(m.start(), m.end(), m.group(0)) for m in _IN_TEXT_RE.finditer(text or "")]


def gaseste(text: str) -> list[str]:
    """Email addresses as written in `text`."""
    return [v for _, _, v in pozitii(text)]


def e_valid(email: str) -> bool:
    return isinstance(email, str) and _INTREG_RE.fullmatch(email.strip()) is not None


def valideaza(email: str, uid: str) -> str | None:
    """"oficial" / "altul" / None (not admitted) — see the module docstring."""
    if not e_valid(email):
        return None
    domeniu = email.strip().lower().rsplit("@", 1)[-1]
    if domeniu == DOMENIU_CAMERA.get(str(uid).split(":", 1)[0]):
        return "oficial"
    if domeniu in DOMENIU_CAMERA.values():
        return None
    return "altul"


def admite(candidati: list, uid: str, cine: str = "") -> tuple[str | None, list[str]]:
    """(official_email, other_emails) built from the admitted candidates."""
    oficial, altele = None, []
    for brut in candidati:
        if not brut:
            continue
        tip = valideaza(brut, uid)
        if tip is None:
            log.warning("email neadmis: %r (%s %s)", brut, uid, cine)
            continue
        email = brut.strip()
        if tip == "oficial":
            oficial = oficial or email
        elif email.lower() not in (a.lower() for a in altele):
            altele.append(email)
    return oficial, altele
