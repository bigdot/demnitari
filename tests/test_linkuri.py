from scrapers import linkuri


def test_url_valid_primeste_protocol():
    assert linkuri.normalizeaza_url("oanamurariu.ro/audiente") == "https://oanamurariu.ro/audiente"
    assert linkuri.normalizeaza_url(" http://sighiartau.ro/ ") == "http://sighiartau.ro/"


def test_ce_nu_e_url_e_respins():
    # cazul real (Coleşa): host fara TLD, inventat de model
    assert linkuri.normalizeaza_url("https://camera-deputaţilor/alin-colesa") is None
    for rau in ("Călin Gal", "Mihai-Cosmin Pascariu", "", None, 5, "ftp://x.ro", "mailto:a@b.ro"):
        assert linkuri.normalizeaza_url(rau) is None


def test_clasifica_dupa_host_nu_dupa_substring():
    assert linkuri.clasifica("https://www.youtube.com/@allencoliban") == "youtube"
    assert linkuri.clasifica("https://m.facebook.com/x") == "facebook"
    assert linkuri.clasifica("https://twitter.com/x") == "x"
    assert linkuri.clasifica("https://www.linux.com/") == "site"  # "x.com" e doar in coada
    assert linkuri.clasifica("https://ionpop.ro/despre-facebook") == "site"


def test_website_care_e_retea_sociala_trece_la_socials():
    # cazul real (Coliban): canalul de YouTube trecut ca website
    c = {"website": "https://www.youtube.com/@allencoliban", "socials": []}
    linkuri.normalizeaza(c)
    assert c == {"website": None,
                 "socials": [{"youtube": "https://www.youtube.com/@allencoliban"}]}


def test_socials_invalide_scoase_reteaua_corectata_si_dedupe():
    c = {"website": "ionpop.ro", "socials": [
        {"facebook": "Ion Pop"},                           # nume, nu URL
        {"facebook": "www.instagram.com/ionpop"},          # eticheta gresita
        {"instagram": "https://instagram.com/ionpop/"},    # dublura
        {"telegram": "https://t.me/ionpop"},               # retea necunoscuta: ramane
    ]}
    linkuri.normalizeaza(c)
    assert c == {"website": "https://ionpop.ro", "socials": [
        {"instagram": "https://www.instagram.com/ionpop"},
        {"telegram": "https://t.me/ionpop"},
    ]}
