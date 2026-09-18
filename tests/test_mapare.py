from pathlib import Path

import pytest

from scrapers.cdep import parse_lista
from scrapers.mapare import mapeaza_senatori
from scrapers.senat import parse_lista_senatori

FIXTURES = Path(__file__).parent / "fixtures"


def test_lista_senatori_de_pe_senat_ro():
    html = (FIXTURES / "senat_lista.html").read_text(encoding="utf-8", errors="replace")
    senatori = parse_lista_senatori(html)
    assert len(senatori) == 134  # dedup: cardurile apar de mai multe ori in pagina
    dobra = next(s for s in senatori if s["guid"] == "5cb3f164-6f0c-449b-bc2e-457c5e9bf73c")
    assert dobra["nume"] == "DOBRA Elena-Adelina"


def test_maparea_e_completa_1_la_1():
    cdep = parse_lista(
        (FIXTURES / "cdep_par_c_senat.html").read_text(encoding="utf-8", errors="replace")
    )
    senat = parse_lista_senatori(
        (FIXTURES / "senat_lista.html").read_text(encoding="utf-8", errors="replace")
    )
    mapare = mapeaza_senatori(cdep, senat)
    assert len(mapare) == 134
    assert len(set(mapare.values())) == 134


def test_bolojan_prins_de_fallback():
    # cdep: "Bolojan Ilie-Gavril" / senat.ro: "BOLOJAN Ilie" — match pe subset de tokens
    cdep = parse_lista(
        (FIXTURES / "cdep_par_c_senat.html").read_text(encoding="utf-8", errors="replace")
    )
    senat = parse_lista_senatori(
        (FIXTURES / "senat_lista.html").read_text(encoding="utf-8", errors="replace")
    )
    mapare = mapeaza_senatori(cdep, senat)
    bolojan_idm = next(
        s["idm"] for c in cdep for s in c["deputati"] if s["nume_complet"].startswith("Bolojan")
    )
    guid = mapare[bolojan_idm]
    bolojan_senat = next(s for s in senat if s["guid"] == guid)
    assert bolojan_senat["nume"] == "BOLOJAN Ilie"


def test_senator_lipsa_da_eroare():
    cdep = parse_lista(
        (FIXTURES / "cdep_par_c_senat.html").read_text(encoding="utf-8", errors="replace")
    )
    senat = parse_lista_senatori(
        (FIXTURES / "senat_lista.html").read_text(encoding="utf-8", errors="replace")
    )
    del senat[0]
    with pytest.raises(ValueError, match="nemapat"):
        mapeaza_senatori(cdep, senat)
