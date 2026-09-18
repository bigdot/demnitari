from pathlib import Path

import pytest

from scrapers.cdep import parse_lista

FIXTURE = Path(__file__).parent / "fixtures" / "cdep_par_c_senat.html"


@pytest.fixture(scope="module")
def lista():
    return parse_lista(FIXTURE.read_text(encoding="utf-8", errors="replace"))


def test_toate_circumscriptiile_prezente(lista):
    assert len(lista) == 43
    assert lista[13]["nr"] == 14
    assert lista[13]["nume"] == "CONSTANŢA"


def test_numarul_total_de_senatori(lista):
    toti = [s for c in lista for s in c["deputati"]]
    assert len(toti) == 134
    assert len({s["idm"] for s in toti}) == 134


def test_senator_constanta(lista):
    constanta = lista[13]["deputati"]
    stroe = next(s for s in constanta if s["idm"] == 109)
    assert stroe["nume_complet"] == "Stroe Felix"
    assert stroe["grup"] == "PSD"
    assert stroe["email"] is None
    assert "cam=1" in stroe["profil_url"]


def test_niciun_email_publicat_in_lista_senatului(lista):
    toti = [s for c in lista for s in c["deputati"]]
    assert all(s["email"] is None for s in toti)
