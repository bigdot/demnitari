"""Phone numbers, in one place — backed by libphonenumber, no homemade regexes.

  - gaseste(text): numbers found in free text (mechanical extraction; respects
    digit boundaries, so a slice of a Facebook id is not a phone).
  - normalizeaza(numere): the FINAL step of the build, over every member no
    matter where the number came from (mechanical, LLM, cache): valid RO/intl
    numbers -> E.164 (+40...), deduplicated; anything invalid is dropped.
"""

from __future__ import annotations

import logging

import phonenumbers

log = logging.getLogger("demnitari.telefoane")

REGIUNE = "RO"


def pozitii(text: str) -> list[tuple[int, int, str]]:
    """(start, end, number as written) for every phone number in `text`."""
    return [(m.start, m.end, m.raw_string)
            for m in phonenumbers.PhoneNumberMatcher(text or "", REGIUNE)]


def gaseste(text: str) -> list[str]:
    """Phone numbers as written in `text` (raw; normalizeaza() runs at the end)."""
    return [v for _, _, v in pozitii(text)]


def normalizeaza(numere: list[str], cine: str = "") -> list[str]:
    out: list[str] = []
    for brut in numere or []:
        try:
            nr = phonenumbers.parse(brut, REGIUNE)
        except phonenumbers.NumberParseException:
            nr = None
        if nr is None or not phonenumbers.is_valid_number(nr):
            log.warning("telefon invalid, scos: %r (%s)", brut, cine)
            continue
        e164 = phonenumbers.format_number(nr, phonenumbers.PhoneNumberFormat.E164)
        if e164 not in out:
            out.append(e164)
    return out
