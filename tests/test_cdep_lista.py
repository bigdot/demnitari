from pathlib import Path

import pytest

from scrapers.cdep import parse_lista

FIXTURE = Path(__file__).parent / "fixtures" / "cdep_par_c.html"


@pytest.fixture(scope="module")
def lista():
    return parse_lista(FIXTURE.read_text(encoding="utf-8", errors="replace"))


def test_toate_circumscriptiile_prezente(lista):
    assert len(lista) == 43
    assert lista[0]["nr"] == 1
    assert lista[0]["nume"] == "ALBA"
    assert lista[42]["nr"] == 43
    assert lista[42]["nume"] == "DIASPORA"


def test_numarul_total_de_deputati(lista):
    toti = [d for c in lista for d in c["deputati"]]
    assert len(toti) == 330
    # idm unic per deputat
    assert len({d["idm"] for d in toti}) == 330


def test_deputat_cu_email(lista):
    alba = lista[0]["deputati"]
    gavrila = next(d for d in alba if d["idm"] == 114)
    assert gavrila["nume_complet"] == "Gavrilă Bianca-Eugenia"
    assert gavrila["grup"] == "UPR"
    assert gavrila["email"] == "bianca.gavrila@cdep.ro"
    assert (
        gavrila["profil_url"]
        == "https://www.cdep.ro/ords/pls/parlam/structura2015.mp?idm=114&cam=2&leg=2024"
    )


def test_deputat_fara_email(lista):
    alba = lista[0]["deputati"]
    bara = next(d for d in alba if d["nume_complet"] == "Bara Nicolae-Adrian")
    assert bara["grup"] == "PSD"
    assert bara["afiliat_grup"] is False
    assert bara["email"] is None


def test_membru_afiliat_la_grup_e_separat(lista):
    # celula "PSD<br>afiliat" nu se lipeste in "PSDafiliat"
    toti = [d for c in lista for d in c["deputati"]]
    gavrilescu = next(d for d in toti if d["nume_complet"].startswith("Gavrilescu"))
    assert gavrilescu["grup"] == "PSD"
    assert gavrilescu["afiliat_grup"] is True
