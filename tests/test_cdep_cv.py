from pathlib import Path

from scrapers.cdep import cv_contacte, cv_text, parse_cv

FIXTURES = Path(__file__).parent / "fixtures"


def cv(nume: str) -> dict:
    html = (FIXTURES / f"cv_{nume}.html").read_text(encoding="utf-8", errors="replace")
    return parse_cv(html)


def test_cv_europass_email_si_facebook():
    c = cv("adomnicai")
    assert c["email"] == "mirela_adomnicai@yahoo.com"
    assert c["facebook"] == "https://www.facebook.com/mirelaelena.adomnicai"


def test_cv_format_vechi_doar_email():
    c = cv("fifor")
    assert c["email"] == "mfifor@yahoo.com"
    assert "facebook" not in c


def test_cv_text_da_textul_curat_pentru_llm():
    # textul brut al CV-ului (chrome scos) pentru stage 2 — LLM-ul il primeste
    html = (FIXTURES / "cv_fifor.html").read_text(encoding="utf-8", errors="replace")
    t = cv_text(html)
    assert "mfifor@yahoo.com" in t         # continutul propriu-zis ramane
    assert "cameradeputatilor" not in t    # chrome-ul institutiei scos


def test_cv_text_incepe_cu_cv_ul_nu_cu_meniul_site_ului():
    html = (FIXTURES / "cv_fifor.html").read_text(encoding="utf-8", errors="replace")
    t = cv_text(html)
    assert "Deputaţi în ordine alfabetică" not in t  # coloana de navigare, scoasa
    assert t.index("Curriculum Vitae") < 100


# --- cv_contacte: ce pleaca din CV spre LLM (antet + contactele gasite, in context) ---

_UMPLUTURA = "Activitate si responsabilitati diverse in cadrul institutiei. " * 20  # ~1200 car.


def test_cv_contacte_antetul_pleaca_textual():
    text = "Ion POP Curriculum Vitae E-mail ion@yahoo.com Web www.ionpop.ro " + _UMPLUTURA
    out = cv_contacte(text)
    assert out.startswith("ANTET: Ion POP Curriculum Vitae E-mail ion@yahoo.com")
    assert "CONTACT" not in out  # ce e in antet nu se mai listeaza inca o data


def test_cv_contacte_gaseste_contactul_de_la_coada_cu_context():
    # cazul real (Tanasă): blogul personal era dupa caracterul 5000, se pierdea la cap
    text = ("Ion POP Curriculum Vitae " + _UMPLUTURA * 8
            + "Editor al blogului www.ionpop.ro , peste 2000 de articole publicate.")
    assert len(text) > 9000
    out = cv_contacte(text)
    linie = [l for l in out.splitlines() if l.startswith("CONTACT")]
    assert len(linie) == 1
    assert "[url: www.ionpop.ro]" in linie[0]
    assert "Editor al blogului" in linie[0]  # contextul din care modelul decide al cui e
    assert len(out) < 1200                   # nu tot CV-ul


def test_cv_contacte_grupeaza_ce_sta_in_acelasi_loc_si_scoate_dublurile():
    text = ("Ion POP Curriculum Vitae " + _UMPLUTURA
            + "Liceul X, tel. 0257231726, email: liceu@yahoo.ro , web: https://liceu.ro " + _UMPLUTURA
            + "Absolvent al Liceului X ( https://liceu.ro )")
    linii = [l for l in cv_contacte(text).splitlines() if l.startswith("CONTACT")]
    assert len(linii) == 1  # un singur loc; a doua aparitie a lui liceu.ro nu se repeta
    assert "telefon: 0257231726; email: liceu@yahoo.ro; url: https://liceu.ro" in linii[0]


def test_cv_contacte_domeniul_unui_email_nu_e_link():
    text = "Ion POP Curriculum Vitae " + _UMPLUTURA + "E-mail personal ion@ionpop.ro si atat."
    linii = [l for l in cv_contacte(text).splitlines() if l.startswith("CONTACT")]
    assert linii and "[email: ion@ionpop.ro]" in linii[0]


def test_cv_contacte_cv_gol():
    assert cv_contacte("") == ""


def test_fara_zgomot_institutional():
    # linkurile Camerei (facebook/twitter/instagram/youtube din header+footer)
    # nu sunt contactele deputatului
    for nume in ("adomnicai", "fifor"):
        c = cv(nume)
        for v in c.values():
            assert "cameradeputatilor" not in v
            assert "cdep_ro" not in v
            assert "Parlamentul-Romaniei" not in v
