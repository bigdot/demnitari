"""Match senators between cdep.ro (idm) and senat.ro (GUID) by name.

There is no shared id between the two sites, so matching is by normalized
name (diacritics stripped, uppercased, hyphens as spaces, tokens sorted —
name order differs: cdep "Bolojan Ilie-Gavril" vs senat.ro "BOLOJAN Ilie").

Two passes:
  1. exact normalized match (133/134 as of 2026-09),
  2. unique token-subset match for name variants (senat.ro drops Bolojan's
     middle name: {BOLOJAN, ILIE} ⊆ {BOLOJAN, ILIE, GAVRIL}).
Anything still unmatched or ambiguous raises — the build must fail rather
than publish a wrong join.
"""

from __future__ import annotations

import logging
import re
import unicodedata

log = logging.getLogger("demnitari.mapare")


def _norm_tokens(nume: str) -> frozenset[str]:
    n = unicodedata.normalize("NFKD", nume)
    n = "".join(c for c in n if not unicodedata.combining(c))
    return frozenset(t for t in re.split(r"[\s-]+", n.upper()) if t)


def mapeaza_senatori(cdep_lista: list[dict], senat_lista: list[dict]) -> dict[int, str]:
    """-> {idm (cdep.ro): guid (senat.ro)}; raises ValueError if not 1:1."""
    senat = {s["guid"]: _norm_tokens(s["nume"]) for s in senat_lista}
    ramas = dict(senat)
    mapare: dict[int, str] = {}
    nemapati: list[dict] = []

    membri = [s for c in cdep_lista for s in c["deputati"]]
    for m in membri:
        tokens = _norm_tokens(m["nume_complet"])
        exact = [g for g, t in ramas.items() if t == tokens]
        if len(exact) == 1:
            mapare[m["idm"]] = exact[0]
            del ramas[exact[0]]
        else:
            nemapati.append(m)

    for m in nemapati:
        tokens = _norm_tokens(m["nume_complet"])
        candidati = [g for g, t in ramas.items() if t <= tokens or tokens <= t]
        if len(candidati) != 1:
            raise ValueError(
                f"senator nemapat sau ambiguu: {m['nume_complet']!r} "
                f"(candidati: {len(candidati)})"
            )
        mapare[m["idm"]] = candidati[0]
        del ramas[candidati[0]]

    if ramas:
        # senat.ro are senatori care nu-s in lista cdep (lista cdep incompleta) —
        # e validare, nu build: logam; valideaza/MIN_SENATORI gatuie o lista prea mica
        log.warning("%d senatori de pe senat.ro nemapati: %s", len(ramas), list(ramas)[:3])
    return mapare
