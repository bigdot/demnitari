"""Build site/data/localitati.json from the official SIRUTA nomenclature.

Source: INS via data.gov.ro (CSV, semicolon-separated, utf-8 with BOM,
ALL-CAPS names with legacy cedilla diacritics Ş/Ţ). A new resource is
published every semester under a new dataset id — update SIRUTA_URL then.

Row levels (NIV):
  1 = county   ("JUDEŢUL ALBA", plus "MUNICIPIUL BUCUREŞTI" for jud 40)
      -> only used to map SIRUTA's own county codes (Cluj=12, Călărași=51,
         Giurgiu=52 — NOT the electoral order) to circumscription codes
  2 = administrative units ("MUNICIPIUL TURDA") — skipped: they duplicate
      their NIV-3 seat locality and users don't type "municipiul"
  3 = actual localities (cities proper, villages, Bucharest sectors)

Each output entry carries a precomputed "cauta" form (lowercase, no
diacritics) so the frontend autocomplete needs no unicode logic.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata

from scrapers.circumscriptii import CIRCUMSCRIPTII

SIRUTA_URL = (
    "https://data.gov.ro/dataset/721c9059-5f87-4c79-9854-a1d5c18f58d5/"
    "resource/dac903f0-32b5-489a-89e7-2c80d96cf68d/download/siruta_s1_2026.csv"
)

# words kept lowercase inside names (Valea lui Mihai, Baia de Arieş...)
_CONECTIVE = {"lui", "de", "din", "la", "cu", "pe", "sub", "cel", "lu"}

_CEDILE = str.maketrans({"Ş": "Ș", "ş": "ș", "Ţ": "Ț", "ţ": "ț"})


def _fara_diacritice(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c))


def _titlecase_ro(nume: str) -> str:
    cuvinte = []
    for i, cuvant in enumerate(nume.lower().split()):
        if i > 0 and cuvant in _CONECTIVE:
            cuvinte.append(cuvant)
        else:
            # capitalize each hyphenated part: cluj-napoca -> Cluj-Napoca
            cuvinte.append("-".join(p.capitalize() for p in cuvant.split("-")))
    return " ".join(cuvinte)


def construieste_localitati(csv_text: str) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(csv_text), delimiter=";"))

    # SIRUTA county code -> circumscription code, matched by county name
    circ_dupa_nume = {
        _fara_diacritice(c["nume"]).upper(): c["cod"] for c in CIRCUMSCRIPTII
    }
    jud_cod: dict[str, str] = {}
    for r in rows:
        if r["NIV"] != "1":
            continue
        nume = re.sub(r"^JUDE\S+\s+", "", r["DENLOC"])  # "JUDEŢUL ALBA" -> "ALBA"
        if "BUCURE" in nume:
            jud_cod[r["JUD"]] = "B"
        else:
            jud_cod[r["JUD"]] = circ_dupa_nume[_fara_diacritice(nume).upper()]

    localitati = []
    for r in rows:
        if r["NIV"] != "3":
            continue
        nume = _titlecase_ro(r["DENLOC"].translate(_CEDILE))
        localitati.append(
            {
                "nume": nume,
                "judet": jud_cod[r["JUD"]],
                "siruta": int(r["SIRUTA"]),
                "cauta": _fara_diacritice(nume).lower(),
                # SIRUTA TIP as a rank: lower = more urban (9 = oraș reședință de
                # municipiu, 22/23 = sate). Used to order same-name matches so the
                # city Galați beats the village Galați din Alba.
                "rang": int(r["TIP"]),
            }
        )

    localitati.append(
        {
            # cdep files national-minority MPs under the Diaspora circumscription
            # (43), so this entry covers both — searching "minoritati" finds it.
            "nume": "Diaspora (în afara țării) sau minorități naționale",
            "judet": "DIA",
            "siruta": 0,
            "cauta": "diaspora in afara tarii sau minoritati nationale",
            "rang": 0,
        }
    )
    return localitati


if __name__ == "__main__":
    import os
    import sys

    from scrapers.fetch import Fetcher

    out = sys.argv[1] if len(sys.argv) > 1 else "site/data/localitati.json"
    # data.gov.ro serves no charset header; requests would fall back to
    # ISO-8859-1 and mangle diacritics — the file is UTF-8 with BOM.
    csv_text = Fetcher().get(SIRUTA_URL).content.decode("utf-8-sig")
    localitati = construieste_localitati(csv_text)
    assert len(localitati) > 12000, f"suspect de putine localitati: {len(localitati)}"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)  # data/ e generat, poate lipsi
    with open(out, "w", encoding="utf-8") as f:
        json.dump(localitati, f, ensure_ascii=False, separators=(",", ":"))
    print(f"ok: {len(localitati)} localitati in {out}")
