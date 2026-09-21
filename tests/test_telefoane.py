import pytest

from scrapers import telefoane


@pytest.mark.parametrize("brut,asteptat", [
    ("0726.200.645", "+40726200645"),      # national cu puncte
    ("0726200645", "+40726200645"),        # national lipit
    ("0726 200 645", "+40726200645"),      # national cu spatii
    ("+40 723 257 640", "+40723257640"),   # international cu spatii
    ("+ 40 723 257 640", "+40723257640"),  # plus rupt de spatiu
    ("(+40) 234588884", "+40234588884"),   # prefix in paranteze
    ("0040726200645", "+40726200645"),     # 00 in loc de +
    ("0364 808 736", "+40364808736"),      # fix Cluj
    ("021 414 27 09", "+40214142709"),     # fix Bucuresti
])
def test_normalizeaza_la_e164(brut, asteptat):
    assert telefoane.normalizeaza([brut]) == [asteptat]


def test_normalizeaza_deduplica_aceeasi_cifra_in_formatari_diferite():
    assert telefoane.normalizeaza(["0726.200.645", "0726 200 645", "+40 723 257 640"]) == [
        "+40726200645", "+40723257640"]


@pytest.mark.parametrize("gunoi", [
    "0006735532",          # felie din ID-ul de Facebook al lui Cosa
    "0508997436",          # idem, Abrudean
    "065275904",           # prea scurt
    "sunati la cabinet",   # text de la LLM
    "",
])
def test_normalizeaza_scoate_ce_nu_e_numar_valid(gunoi):
    assert telefoane.normalizeaza([gunoi]) == []


def test_gaseste_numarul_din_text_liber():
    assert telefoane.gaseste("Telefon:\xa00712212558") == ["0712212558"]
    assert telefoane.gaseste("🗓️Programare: 📞0364 808 736 sau 🌐 oanamurariu.ro") == ["0364 808 736"]


@pytest.mark.parametrize("text", [
    "https://www.facebook.com/profile.php?id=100067355326622",   # cazul real Cosa
    "www.facebook.com/Abrudean-Mircea-105089974364982",          # cazul real Abrudean
    "n. 11 sep. 1988, HCD nr.109/2024, idm=213",
])
def test_gaseste_nu_ia_felii_din_alte_siruri_de_cifre(text):
    assert telefoane.gaseste(text) == []
