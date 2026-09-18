import json
from pathlib import Path

import pytest

from scrapers import receipt as R
from scrapers.build import ruleaza

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _run_in_tmp(tmp_path, monkeypatch):
    # ruleaza scrie run/receipt.json cu run_dir="run" (relativ) — muta cwd in
    # tmp ca receipt-ul sa aterizeze izolat, nu in ./run din repo
    monkeypatch.chdir(tmp_path)


class _Resp:
    def __init__(self, text):
        self.text = text


class _FetcherFixture:
    """Serveste fixture-urile locale: listele reale, iar pentru cele ~464
    de profiluri/CV-uri/biografii intoarce mereu aceleasi pagini-exemplu."""

    def get(self, url, **kw):
        if "par=C&cam=1" in url or ("par=C" in url and "cam=1" in url):
            return _Resp((FIXTURES / "cdep_par_c_senat.html").read_text(errors="replace"))
        if "par=C" in url:
            return _Resp((FIXTURES / "cdep_par_c.html").read_text(errors="replace"))
        if "FisaSenatori.aspx" in url:
            return _Resp((FIXTURES / "senat_lista.html").read_text(errors="replace"))
        if "FisaSenator.aspx" in url:
            return _Resp((FIXTURES / "senat_fisa_dobra.html").read_text(errors="replace"))
        if "pag=0" in url:
            return _Resp((FIXTURES / "cv_fifor.html").read_text(errors="replace"))
        if "structura2015.mp" in url:
            return _Resp((FIXTURES / "profil_fifor.html").read_text(errors="replace"))
        raise AssertionError(f"URL neasteptat: {url}")

    def post(self, url, data, **kw):
        assert "FisaSenator.aspx" in url
        return _Resp((FIXTURES / "senat_biografie_dobra.html").read_text(errors="replace"))


def test_ruleaza_cap_coada(tmp_path):
    ruleaza(_FetcherFixture(), tmp_path, leg=2024)

    fisiere = sorted(p.name for p in (tmp_path / "parlamentari").glob("*.json"))
    assert len(fisiere) == 43

    cj = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    assert cj["circumscriptie"] == {"cod": "CJ", "nume": "Cluj", "nr": 13}
    assert len(cj["deputati"]) == 10
    assert len(cj["senatori"]) == 4
    # merge listă + profil: grupul scurt din listă, istoricul din profil
    d = cj["deputati"][0]
    assert "grup" in d and "grup_long" in d and "partide_precedente" in d
    # merge bio senat.ro: telefonul din biografie
    s = cj["senatori"][0]
    assert "0791650126" in s["contacts"]["numbers"]

    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["deputati"] == 330
    assert meta["senatori"] == 134


class _ClientNumara:
    """Client batch fals: numara cererile (batch-uri), nu membrii."""

    def __init__(self):
        self.cereri = 0

    def rafineaza_batch(self, membri):
        self.cereri += 1
        return {str(m["id"]): {"contacts": {"offices": ["Birou rafinat LLM"]}}
                for m in membri}


def test_llm_batch_prima_data_si_cache_a_doua(tmp_path):
    c1 = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c1)
    # 464 membri / 50 per batch = 10 cereri, nu 464
    assert c1.cereri == 10
    cj = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    assert cj["deputati"][0]["contacts"]["offices"] == ["Birou rafinat LLM"]
    assert cj["deputati"][0]["profile_text_hash"]

    # a doua rulare: precedentul are aceleasi hash-uri -> zero cereri LLM
    c2 = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c2)
    assert c2.cereri == 0
    cj2 = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    assert cj2["deputati"][0]["contacts"]["offices"] == ["Birou rafinat LLM"]


class _ClientCaptura:
    """Client batch fals care retine payload-urile trimise catre LLM."""

    def __init__(self):
        self.payloads = []

    def rafineaza_batch(self, membri):
        self.payloads.extend(membri)
        return {}


def test_llm_primeste_textul_cv(tmp_path):
    c = _ClientCaptura()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c)
    assert c.payloads
    # fixture-ul serveste CV-ul lui Fifor pentru toti -> textul CV ajunge la LLM
    assert any("mfifor@yahoo.com" in (m.get("cv") or "") for m in c.payloads)


def test_json_sters_reface_totul(tmp_path):
    # invalidarea la schimbare de schema = stergi JSON-ul -> fara precedent -> re-ruleaza tot
    c1 = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c1)
    assert c1.cereri == 10

    import shutil
    shutil.rmtree(tmp_path / "parlamentari")
    c2 = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c2)
    assert c2.cereri == 10  # niciun precedent -> toti din nou


def test_fara_client_build_ul_merge_fara_rafinare(tmp_path):
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=None)
    cj = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    assert cj["deputati"][0]["_rafinare"] is None


def test_textele_de_profil_se_curata(tmp_path):
    import glob
    import tempfile

    inainte = set(glob.glob(f"{tempfile.gettempdir()}/demnitari_profil_*"))
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=None)
    dupa = set(glob.glob(f"{tempfile.gettempdir()}/demnitari_profil_*"))
    assert inainte == dupa  # niciun director tmp lasat in urma


class _FetcherCvStricat(_FetcherFixture):
    """CV-urile dau HTTP 555 (cazul real Tepelus, sept 2026)."""

    def get(self, url, **kw):
        if "pag=0" in url:
            raise RuntimeError("555 Server Error")
        return super().get(url, **kw)


def test_cv_stricat_nu_omoara_build_ul(tmp_path):
    ruleaza(_FetcherCvStricat(), tmp_path, leg=2024)
    cj = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    d = cj["deputati"][0]
    assert d["cv_url"] is None  # nu trimitem userii pe pagina 555
    assert d["contacts"]["other_emails"] == []  # fara CV, fara email personal


class _FetcherProfilTranzitoriu(_FetcherFixture):
    """Primul fetch al fiecarui profil intoarce pagina goala (200 fara
    continut — cazul real din 16 sept 2026), al doilea pagina buna."""

    def __init__(self):
        self.esuate = set()

    def get(self, url, **kw):
        if "structura2015.mp" in url and "pag=0" not in url and url not in self.esuate:
            self.esuate.add(url)
            return _Resp("<html><body>gol</body></html>")
        return super().get(url, **kw)


def test_profil_invalid_tranzitoriu_se_reincearca(tmp_path, monkeypatch):
    monkeypatch.setattr("scrapers.build._PAUZE_REFETCH", (0,))
    ruleaza(_FetcherProfilTranzitoriu(), tmp_path, leg=2024)
    cj = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    assert cj["deputati"][0]["nume"] == "FIFOR"


# --- moduri: daily / continue / all ---

def test_daily_scrie_receipt_complet(tmp_path):
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    rec = R.incarca("run")  # cwd = tmp_path (autouse)
    assert rec is not None and len(rec["membri"]) == 464
    assert R.e_complet(rec)


def test_continue_reia_doar_incompletii(tmp_path):
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    # marcheaza 2 membri ca stage2 nefacut
    rec = R.incarca("run")
    uids = list(rec["membri"])[:2]
    for u in uids:
        R.marcheaza(rec, u, s2=False)
    R.salveaza("run", rec)

    cap = _ClientCaptura()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=cap, mod="continue")
    # doar cei 2 incompleti ajung la LLM; restul refolositi din publicarea anterioara
    assert {m["id"] for m in cap.payloads} == set(uids)
    # attempts a crescut
    assert R.incarca("run")["attempts"] == 2


def test_all_forteaza_tot_si_nu_scrie_receipt(tmp_path):
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    run_all = tmp_path / "run_all"
    c = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c, mod="all", run_dir=run_all)
    assert c.cereri == 10  # ignora cache-ul, re-trimite toti 464
    assert not (run_all / "receipt.json").exists()  # --all nu scrie receipt


class _ClientGol:
    """LLM care nu corecteaza pe nimeni (intoarce {} — niciun id in raspuns)."""

    def __init__(self):
        self.cereri = 0

    def rafineaza_batch(self, membri):
        self.cereri += 1
        return {}


def test_membru_curat_e_cache_hit_a_doua_oara(tmp_path):
    # fix churn: membrii pe care LLM-ul nu-i schimba primesc _rafinare={} (nu None)
    c1 = _ClientGol()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c1)
    assert c1.cereri == 10
    cj = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    assert cj["deputati"][0]["_rafinare"] == {}  # curat, dar cache-abil
    # a doua rulare: toti cache hit -> zero cereri (fara fix ar fi 10 din nou)
    c2 = _ClientGol()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c2)
    assert c2.cereri == 0


def test_fetch_lista_cdep_reincearca_pe_gol(monkeypatch):
    from scrapers.build import _fetch_lista_cdep

    monkeypatch.setattr("scrapers.build._PAUZE_REFETCH", (0, 0))
    good = (FIXTURES / "cdep_par_c.html").read_text(errors="replace")

    class F:
        def __init__(self):
            self.n = 0

        def get(self, url, **kw):
            self.n += 1
            return _Resp("<html></html>") if self.n == 1 else _Resp(good)

    f = F()
    circ = _fetch_lista_cdep(f, "http://x", robust=True)
    assert sum(len(c["deputati"]) for c in circ) > 0 and f.n == 2  # a reincercat
    f2 = F()
    circ2 = _fetch_lista_cdep(f2, "http://x", robust=False)
    assert sum(len(c["deputati"]) for c in circ2) == 0 and f2.n == 1  # --all nu reincearca
