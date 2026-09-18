from pathlib import Path

import pytest

from scrapers.cdep import parse_profil

FIXTURES = Path(__file__).parent / "fixtures"


def profil(nume: str) -> dict:
    html = (FIXTURES / f"profil_{nume}.html").read_text(encoding="utf-8", errors="replace")
    return parse_profil(html)


def test_nume_prenume_din_majuscule():
    p = profil("fifor")
    assert p["nume"] == "FIFOR"
    assert p["prenume"] == "Mihai-Viorel"


def test_nume_cu_diacritice_majuscule():
    p = profil("adomnicai")
    assert p["nume"] == "ADOMNICĂI"
    assert p["prenume"] == "Mirela Elena"


def test_partid_si_grup_fara_istoric():
    p = profil("fifor")
    assert p["partid"] == "Partidul Social Democrat"
    assert p["partide_precedente"] == {}
    assert p["grup_parlamentar"] == "Grupul parlamentar al Partidului Social Democrat"
    assert p["grupuri_parlamentare_precedente"] == {}
    assert p["afiliat"] is True


def test_traseist_cu_istoric():
    p = profil("nagy")
    assert p["partid"].startswith("Fără adeziune")
    assert p["partide_precedente"] == {"2024-12_2026-06": "Partidul S.O.S. România"}
    assert p["grup_parlamentar"] == "Deputaţi neafiliaţi"
    assert p["grupuri_parlamentare_precedente"] == {
        "2024-12_2026-06": "Grupul parlamentar SOS România"
    }
    assert p["afiliat"] is False


def test_foto_si_circumscriptie():
    p = profil("fifor")
    assert p["foto"] == "https://www.cdep.ro/parlamentari/l2024/FiforMihaiViorel.JPG"
    assert p["circumscriptie_nr"] == 2


def test_cv_url_prezent_si_absent():
    assert profil("fifor")["cv_url"] is not None
    assert "pag=0" in profil("fifor")["cv_url"]
    assert profil("gavrila")["cv_url"] is None


def test_birouri():
    assert profil("fifor")["birouri"] == ["Arad, Bld. Revolutiei, Nr. 74, Jud. Arad"]
    assert len(profil("adomnicai")["birouri"]) == 2
    # randul "email: ..." strecurat in sectiunea de birou nu e adresa
    assert profil("gavrila")["birouri"] == [
        "Str. Regina Maria nr.10, birou 2, Alba Iulia, jud.ALBA"
    ]


def test_profil_senator_acelasi_parser():
    p = profil("stroe")
    assert p["nume"] == "STROE"
    assert p["prenume"] == "Felix"
    assert p["circumscriptie_nr"] == 14
    assert p["birouri"] == []
    assert p["cv_url"] is None


def test_profil_invalid_da_eroare_clara():
    import pytest

    from scrapers.cdep import parse_profil

    with pytest.raises(ValueError, match="mp-profile-name2025"):
        parse_profil("<html><body>ORDS a avut o zi proasta</body></html>")


def test_birourile_raman_linii_brute_pentru_llm():
    # mecanicul nu mai desface emoji/telefon/site — lasa liniile brute pentru
    # stage 2 (LLM). Oana Murariu isi scrie birourile cu emoji; ele raman aici.
    p = profil("murariu")
    assert any("Cluj-Napoca" in b for b in p["birouri"])
    # textul integral al profilului e disponibil ca input pentru LLM
    assert "text_profil" in p and len(p["text_profil"]) > 100
    assert "contacte_birou" not in p
