import json

import pytest

from scrapers.circumscriptii import CIRCUMSCRIPTII, cod_pentru_nr
from scrapers.build import (CV_CAP, _cap_cv, asambleaza_parlamentar,
                            scrie_sigle, valideaza)


class _FetcherSigle:
    """Intoarce cateva bytes pentru orice URL de logo."""

    def get(self, url, **kw):
        return type("R", (), {"content": b"GIF89a-fake"})()


def test_scrie_sigle_copiaza_indep_din_assets(tmp_path):
    # fara logo cdep -> doar sigla manuala; se copiaza din scrapers/assets/
    class _FaraLogo:
        def get(self, url, **kw):
            raise AssertionError("n-ar trebui sa descarce nimic")

    scrie_sigle({}, tmp_path, _FaraLogo())
    assert (tmp_path / "sigle" / "indep.svg").exists()
    m = json.loads((tmp_path / "sigle" / "manifest.json").read_text())
    assert m["Indep."] == "sigle/indep.svg"


def test_scrie_sigle_face_merge_nu_clobber(tmp_path):
    # prima rulare (full) pune un partid; a doua (ca --continue, partiala) alt
    # partid -> manifestul le pastreaza pe amandoua, nu-l goleste
    scrie_sigle({"Partidul X": "https://www.cdep.ro/aleg/px2020.jpg"}, tmp_path, _FetcherSigle())
    scrie_sigle({"Partidul Y": "https://www.cdep.ro/aleg/py2020.jpg"}, tmp_path, _FetcherSigle())
    m = json.loads((tmp_path / "sigle" / "manifest.json").read_text())
    assert "Partidul X" in m and "Partidul Y" in m
    assert m["Indep."] == "sigle/indep.svg"  # manualul mereu prezent


def test_cv_sub_cap_ramane_neatins():
    scurt = "x" * 20
    assert _cap_cv(scurt) == scurt


def test_cv_peste_cap_e_taiat_si_marcat():
    lung = "y" * (CV_CAP + 500)
    out = _cap_cv(lung)
    assert out.startswith("y" * CV_CAP)
    assert "trunchiat" in out          # LLM-ul stie ca fragmentul e taiat
    assert len(out) < len(lung)


def test_tabelul_circumscriptiilor():
    assert len(CIRCUMSCRIPTII) == 43
    assert cod_pentru_nr(1) == "AB"
    assert cod_pentru_nr(13) == "CJ"
    assert cod_pentru_nr(42) == "B"
    assert cod_pentru_nr(43) == "DIA"
    coduri = [c["cod"] for c in CIRCUMSCRIPTII]
    assert len(set(coduri)) == 43


def _lista_entry(**kw):
    return {
        "idm": 106, "nume_complet": "Fifor Mihai-Viorel", "grup": "PSD",
        "email": None, "linkuri": [], "profil_url": "https://www.cdep.ro/...idm=106",
        **kw,
    }


def _profil(**kw):
    return {
        "nume": "FIFOR", "prenume": "Mihai-Viorel",
        "partid": "Partidul Social Democrat", "partide_precedente": {},
        "grup_parlamentar": "Grupul parlamentar al PSD",
        "grupuri_parlamentare_precedente": {}, "afiliat": True,
        "foto": "https://www.cdep.ro/parlamentari/l2024/F.JPG",
        "circumscriptie_nr": 2, "cv_url": "https://www.cdep.ro/...pag=0",
        "birouri": ["Arad, Bld. Revolutiei, Nr. 74"],
        **kw,
    }


def test_asamblare_deputat_complet():
    p = asambleaza_parlamentar(
        _lista_entry(email="mihai.fifor@cdep.ro", linkuri=["https://www.facebook.com/fifor"]),
        _profil(),
        cv={"email": "mfifor@yahoo.com"},
        bio=None,
    )
    assert p["nume"] == "FIFOR"
    assert p["grup"] == "PSD"  # numele scurt, din lista
    assert p["grup_long"] == "Grupul parlamentar al PSD"
    c = p["contacts"]
    assert c["official_email"] == "mihai.fifor@cdep.ro"
    assert c["offices"] == ["Arad, Bld. Revolutiei, Nr. 74"]
    assert c["other_emails"] == ["mfifor@yahoo.com"]
    assert {"facebook": "https://www.facebook.com/fifor"} in c["socials"]
    assert c["numbers"] == []


def test_partid_mandat_din_primul_partid_precedent():
    # traseist: mandat = prima formatiune (cronologic), nu cea curenta; scurtat
    p = asambleaza_parlamentar(
        _lista_entry(),
        _profil(partid="Partidul Umanist Social Liberal",
                partide_precedente={"2024-12_2025-09": "Partidul Social Democrat"}),
        None, None,
    )
    assert p["partid_mandat"] == "PSD"
    assert p["partid"] == "PUSL"
    assert p["partid_long"] == "Partidul Umanist Social Liberal"


def test_partid_mandat_e_cel_curent_daca_nu_a_schimbat():
    p = asambleaza_parlamentar(
        _lista_entry(),
        _profil(partid="Partidul Social Democrat", partide_precedente={}),
        None, None,
    )
    assert p["partid_mandat"] == "PSD"


def test_fara_partid_devine_independent():
    # a plecat din partid (fara adeziune) si nu e minoritar -> independent
    p = asambleaza_parlamentar(
        _lista_entry(),
        _profil(partid="Fără adeziune la formaţiunea politică POT pentru care a candidat",
                partide_precedente={"2024-12_2025-03": "Partidul Oamenilor Tineri"}),
        None, None,
    )
    assert p["partid"] == "Indep."
    assert p["partid_long"] == "Indep."
    assert p["partid_mandat"] == "POT"  # cu cine a fost ales


def test_minoritar_nu_devine_independent():
    # minoritar fara partid, DAR cu organizatie -> nu e "independent"
    p = asambleaza_parlamentar(
        _lista_entry(),
        _profil(partid=None, partide_precedente={},
                organizatie="Forumul German", grup_parlamentar="Deputaţi neafiliaţi"),
        None, None,
    )
    assert p["partid"] is None
    assert p["organizatie"] == "Forumul German"


def test_hash_e_cifra_de_control_peste_text_si_record():
    baza = asambleaza_parlamentar(_lista_entry(), _profil(text_profil="TEXT"), None, None)

    # acelasi text + acelasi record -> acelasi hash
    la_fel = asambleaza_parlamentar(_lista_entry(), _profil(text_profil="TEXT"), None, None)
    assert baza["profile_text_hash"] == la_fel["profile_text_hash"]

    # text de profil schimbat -> hash schimbat
    alt_text = asambleaza_parlamentar(_lista_entry(), _profil(text_profil="ALT"), None, None)
    assert alt_text["profile_text_hash"] != baza["profile_text_hash"]

    # camp mecanic schimbat (grup), acelasi text -> hash schimbat
    alt_grup = asambleaza_parlamentar(_lista_entry(grup="AUR"), _profil(text_profil="TEXT"), None, None)
    assert alt_grup["profile_text_hash"] != baza["profile_text_hash"]


def test_hash_include_textul_cv():
    # CV-ul ajunge la LLM; o schimbare doar in CV trebuie sa re-declanseze stage 2
    fara = asambleaza_parlamentar(_lista_entry(), _profil(text_profil="T"), None, None)
    cu = asambleaza_parlamentar(_lista_entry(), _profil(text_profil="T"), None, None,
                                cv_text="CV NOU CU TELEFON")
    assert cu["profile_text_hash"] != fara["profile_text_hash"]


def test_asamblare_senator_cu_biografie():
    p = asambleaza_parlamentar(
        _lista_entry(),
        _profil(birouri=[]),
        cv=None,
        bio={"email": "a@senat.ro", "telefon": "0791650126",
             "birouri": ["Str. X nr. 1, Targoviste"]},
    )
    c = p["contacts"]
    assert c["official_email"] == "a@senat.ro"
    assert c["offices"] == ["Str. X nr. 1, Targoviste"]
    assert c["numbers"] == ["0791650126"]


def _circ(nr, n_dep, n_sen):
    return {
        "nr": nr, "cod": cod_pentru_nr(nr),
        "deputati": [{"nume": f"D{i}"} for i in range(n_dep)],
        "senatori": [{"nume": f"S{i}"} for i in range(n_sen)],
    }


def test_validarea_trece_pe_date_plauzibile():
    date = [_circ(nr, 8, 3) for nr in range(1, 44)]
    valideaza(date)  # nu ridica


def test_validarea_pica_pe_prea_putini_deputati():
    date = [_circ(nr, 2, 3) for nr in range(1, 44)]
    with pytest.raises(ValueError, match="deputati"):
        valideaza(date)


def test_validarea_pica_pe_circumscriptie_lipsa():
    date = [_circ(nr, 8, 3) for nr in range(1, 43)]  # fara Diaspora
    with pytest.raises(ValueError, match="43"):
        valideaza(date)


def test_validarea_pica_pe_circumscriptie_goala():
    date = [_circ(nr, 8, 3) for nr in range(1, 44)]
    date[12]["senatori"] = []
    with pytest.raises(ValueError, match="goal"):
        valideaza(date)
