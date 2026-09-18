from pathlib import Path

from scrapers.localitati import construieste_localitati

FIXTURE = Path(__file__).parent / "fixtures" / "siruta_sample.csv"


def _toate():
    return construieste_localitati(FIXTURE.read_text(encoding="utf-8-sig"))


def test_doar_localitati_reale_plus_diaspora():
    # fixture: 42 judete (NIV 1, excluse), 3 UAT-uri (NIV 2, excluse),
    # 6 localitati (NIV 3) + intrarea sintetica Diaspora
    loc = _toate()
    assert len(loc) == 7


def test_titlecase_si_diacritice_moderne():
    loc = _toate()
    turda_cj = next(l for l in loc if l["siruta"] == 55268)
    assert turda_cj["nume"] == "Turda"
    assert turda_cj["judet"] == "CJ"
    assert turda_cj["cauta"] == "turda"
    assert turda_cj["rang"] == 9  # municipiu (TIP 9)
    cluj = next(l for l in loc if l["siruta"] == 54984)
    assert cluj["nume"] == "Cluj-Napoca"
    sector = next(l for l in loc if l["siruta"] == 179141)
    # cedilele SIRUTA (Ş) devin virgulite moderne (ș)
    assert sector["nume"] == "București Sectorul 1"
    assert sector["judet"] == "B"
    assert sector["cauta"] == "bucuresti sectorul 1"


def test_conectivele_raman_mici():
    loc = _toate()
    vlm = next(l for l in loc if l["siruta"] == 32036)
    assert vlm["nume"] == "Valea lui Mihai"
    assert vlm["judet"] == "BH"


def test_coliziunile_de_nume_raman_separate():
    loc = _toate()
    turda = [l for l in loc if l["cauta"] == "turda"]
    assert {l["judet"] for l in turda} == {"CJ", "TL"}


def test_diaspora_prezenta():
    loc = _toate()
    dia = next(l for l in loc if l["judet"] == "DIA")
    assert dia["siruta"] == 0
    assert "diaspora" in dia["cauta"]
