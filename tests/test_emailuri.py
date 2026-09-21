from scrapers import emailuri

DEPUTAT, SENATOR = "2:15", "1:15"


def test_gaseste_adresele_din_text():
    text = "E-mail: ion.pop@cdep.ro, personal ion_pop+cabinet@yahoo.com. Tel 0721 000 000"
    assert emailuri.gaseste(text) == ["ion.pop@cdep.ro", "ion_pop+cabinet@yahoo.com"]


def test_url_ul_cu_arond_nu_e_email():
    # cazul real: cdep a pus un link de tiktok sub mailto:
    url = "https://www.tiktok.com/@dr.andreibaciu"
    assert not emailuri.e_valid(url)
    assert emailuri.gaseste(f"vezi {url} pentru detalii") == []


def test_adresa_lipita_de_un_cuvant_cu_diacritice_nu_e_taiata():
    # cazul real (CV Neacşu): nu scoatem "ti.vpm.mn@gov.ro" din mijlocul cuvantului
    assert emailuri.gaseste("Bucureşti.vpm.mn@gov.ro") == []


def test_forme_invalide():
    for rau in ("contact punct ro", "ion@", "@cdep.ro", "ion@localhost", "ion pop@cdep.ro", None, 5):
        assert not emailuri.e_valid(rau)
        assert emailuri.valideaza(rau, DEPUTAT) is None
    assert emailuri.e_valid("  ion.pop@cdep.ro ")


def test_oficial_e_doar_domeniul_camerei_lui():
    assert emailuri.valideaza("ion.pop@cdep.ro", DEPUTAT) == "oficial"
    assert emailuri.valideaza("Ion.Pop@SENAT.ro", SENATOR) == "oficial"
    assert emailuri.valideaza("psdsenat2016@gmail.com", SENATOR) == "altul"
    assert emailuri.valideaza("ion@mail.cdep.ro.example.com", DEPUTAT) == "altul"


def test_adresa_din_cealalta_camera_nu_e_admisa():
    # cazul real (senatoarea Presură): @cdep.ro din CV-ul de fosta deputata —
    # casuta s-a inchis odata cu mandatul; nu e nici oficiala, nici "alt email"
    assert emailuri.valideaza("alexandra.presura@cdep.ro", SENATOR) is None
    assert emailuri.valideaza("ion.pop@senat.ro", DEPUTAT) is None
    assert emailuri.admite(["alexandra.presura@cdep.ro"], SENATOR) == (None, [])


def test_admite_emailul_de_contact_care_nu_e_de_parlament_ca_email_simplu():
    # cazul real: senat.ro listeaza gmail-ul grupului ca email de contact
    assert emailuri.admite(["psdsenat2016@gmail.com"], SENATOR) == (None, ["psdsenat2016@gmail.com"])


def test_admite_oficialul_oriunde_ar_fi_propus_si_fara_dubluri():
    assert emailuri.admite([None, "ion@yahoo.com", "ion.pop@cdep.ro", "ION@yahoo.com"], DEPUTAT) == (
        "ion.pop@cdep.ro", ["ion@yahoo.com"])


def test_admite_nu_lasa_sa_treaca_ce_nu_e_email():
    assert emailuri.admite(["https://www.tiktok.com/@dr.andreibaciu", "andrei.baciu@cdep.ro",
                            "fara arond"], DEPUTAT) == ("andrei.baciu@cdep.ro", [])
