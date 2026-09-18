from pathlib import Path

from scrapers.cdep import cv_text, parse_cv

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


def test_fara_zgomot_institutional():
    # linkurile Camerei (facebook/twitter/instagram/youtube din header+footer)
    # nu sunt contactele deputatului
    for nume in ("adomnicai", "fifor"):
        c = cv(nume)
        for v in c.values():
            assert "cameradeputatilor" not in v
            assert "cdep_ro" not in v
            assert "Parlamentul-Romaniei" not in v
