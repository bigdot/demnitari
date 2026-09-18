from pathlib import Path

from scrapers.senat import extract_postback_fields, parse_biografie

FIXTURES = Path(__file__).parent / "fixtures"


def test_campurile_de_postback_din_fisa():
    html = (FIXTURES / "senat_fisa_dobra.html").read_text(encoding="utf-8", errors="replace")
    fields = extract_postback_fields(html)
    assert fields["__VIEWSTATE"]
    assert fields["__VIEWSTATEGENERATOR"]
    # senat.ro are EventValidation dezactivat — campul nu exista in pagina
    assert "__EVENTVALIDATION" not in fields
    assert fields["__EVENTTARGET"] == "ctl00$B_Center$Repeater14$ctl00$lnkBiog"


def test_biografia_contine_contactele():
    html = (FIXTURES / "senat_biografie_dobra.html").read_text(
        encoding="utf-8", errors="replace"
    )
    bio = parse_biografie(html)
    assert bio["email"] == "adelina.dobra@senat.ro"
    assert bio["telefon"] == "0791650126"
    assert bio["birouri"] == [
        "Str. Poet Grigore Alexandrescu bl. E1, Targoviste, jud. Dambovita",
        "Bdul Panduri nr. 15, bl. D4, sc. B, ap. 2, Mun. Moreni, jud. Dambovita",
    ]
