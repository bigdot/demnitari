import json
from pathlib import Path

import pytest

import scrapers.build as build
from scrapers import receipt as R
from scrapers.build import ruleaza, valideaza

FIXTURES = Path(__file__).parent / "fixtures"
_fetch_lista_reala = build._fetch_lista_cdep


@pytest.fixture(autouse=True)
def _run_in_tmp(tmp_path, monkeypatch):
    # ruleaza scrie in run/ (relativ) — muta cwd in tmp ca sa nu atinga ./run din repo
    monkeypatch.chdir(tmp_path)


class _Resp:
    def __init__(self, text):
        self.text = text


class _FetcherFixture:
    """Serveste fixture-urile locale: listele reale + aceleasi pagini-exemplu
    pentru orice profil/CV/biografie."""

    def get(self, url, **kw):
        if "par=C" in url and "cam=1" in url:
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


def pick_5_members(circ_list, n=5):
    """Primii n membri din lista parsata (restul circumscriptiilor raman goale)."""
    ramas = n
    out = []
    for c in circ_list:
        pastreaza = c["deputati"][:max(ramas, 0)]
        ramas -= len(pastreaza)
        out.append({**c, "deputati": pastreaza})
    return out


def patch_pick_5_members(monkeypatch):
    """`ruleaza` buildeaza 5 deputati + 5 senatori in loc de 464. Parsarea de
    liste/profile e testata in test_cdep_*; aici testam doar fluxul."""
    monkeypatch.setattr(build, "_fetch_lista_cdep",
                        lambda f, u, r: pick_5_members(_fetch_lista_reala(f, u, r)))


def primul_deputat(out_dir):
    for f in sorted((out_dir / "parlamentari").glob("*.json")):
        d = json.loads(f.read_text())
        if d["deputati"]:
            return d["deputati"][0]
    raise AssertionError("niciun deputat scris")


# --- singurul test cu listele complete (464): merge-ul cap-coada + validarea ---

def test_ruleaza_cap_coada(tmp_path):
    rez = ruleaza(_FetcherFixture(), tmp_path, leg=2024)
    valideaza(rez["circumscriptii"])  # pas separat de build; trece pe date complete

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
    assert "0791650126" in cj["senatori"][0]["contacts"]["numbers"]

    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["deputati"] == 330
    assert meta["senatori"] == 134


# --- restul: 5+5 membri ---

class _ClientNumara:
    """Client LLM fals: numara batch-urile si corecteaza pe toata lumea."""

    def __init__(self):
        self.cereri = 0

    def rafineaza_batch(self, membri):
        self.cereri += 1
        return {str(m["id"]): {"contacts": {"offices": ["Birou rafinat LLM"]}}
                for m in membri}


class _ClientCaptura:
    """Client LLM fals: retine ce i s-a trimis, nu corecteaza nimic."""

    def __init__(self):
        self.payloads = []

    def rafineaza_batch(self, membri):
        self.payloads.extend(membri)
        return {}


def test_llm_un_batch_prima_data_si_cache_a_doua(tmp_path, monkeypatch):
    patch_pick_5_members(monkeypatch)
    c1 = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c1)
    assert c1.cereri == 1  # 10 membri intr-un singur batch, nu 10 cereri
    d = primul_deputat(tmp_path)
    assert d["contacts"]["offices"] == ["Birou rafinat LLM"]
    assert d["profile_text_hash"]

    # a doua rulare: aceleasi hash-uri in publicarea precedenta -> zero LLM
    c2 = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c2)
    assert c2.cereri == 0
    assert primul_deputat(tmp_path)["contacts"]["offices"] == ["Birou rafinat LLM"]


def test_membru_curat_e_cache_hit_a_doua_oara(tmp_path, monkeypatch):
    # membrii pe care LLM-ul nu-i schimba primesc _rafinare={} (nu None), altfel
    # ar fi re-trimisi la fiecare rulare
    patch_pick_5_members(monkeypatch)
    c1 = _ClientCaptura()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c1)
    assert len(c1.payloads) == 10
    assert primul_deputat(tmp_path)["_rafinare"] == {}

    c2 = _ClientCaptura()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c2)
    assert c2.payloads == []


def test_llm_primeste_textul_cv(tmp_path, monkeypatch):
    patch_pick_5_members(monkeypatch)
    c = _ClientCaptura()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c)
    assert any("mfifor@yahoo.com" in (m.get("cv") or "") for m in c.payloads)


def test_json_sters_reface_totul(tmp_path, monkeypatch):
    # fara publicare precedenta nu exista cache -> toti din nou la LLM
    import shutil

    patch_pick_5_members(monkeypatch)
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    shutil.rmtree(tmp_path / "parlamentari")
    c2 = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c2)
    assert c2.cereri == 1


def test_fara_client_build_ul_merge_fara_rafinare(tmp_path, monkeypatch):
    patch_pick_5_members(monkeypatch)
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=None)
    assert primul_deputat(tmp_path)["_rafinare"] is None


class _FetcherCvStricat(_FetcherFixture):
    """CV-urile dau HTTP 555 (cazul real Tepelus, sept 2026)."""

    def get(self, url, **kw):
        if "pag=0" in url:
            raise RuntimeError("555 Server Error")
        return super().get(url, **kw)


def test_cv_stricat_nu_omoara_build_ul(tmp_path, monkeypatch):
    patch_pick_5_members(monkeypatch)
    ruleaza(_FetcherCvStricat(), tmp_path, leg=2024, client=None)
    d = primul_deputat(tmp_path)
    assert d["cv_url"] is None  # nu trimitem userii pe pagina 555
    assert d["contacts"]["other_emails"] == []


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
    patch_pick_5_members(monkeypatch)
    monkeypatch.setattr("scrapers.build._PAUZE_REFETCH", (0,))
    ruleaza(_FetcherProfilTranzitoriu(), tmp_path, leg=2024, client=None)
    assert primul_deputat(tmp_path)["nume"] == "FIFOR"


# --- moduri + persistenta in run/ ---

def test_daily_persista_tot_in_run(tmp_path, monkeypatch):
    patch_pick_5_members(monkeypatch)
    rez = ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    assert rez["incomplet"] == []
    rec = R.incarca("run")
    assert len(rec["membri"]) == 10 and R.e_complet(rec)
    # ce s-a scrapat ramane pe disc (fara cleanup): entitati + texte pt LLM
    assert len(list(Path("run/membri").glob("*.json"))) == 10
    assert list(Path("run/texte").glob("*.txt"))


class _FetcherNumaraProfile(_FetcherFixture):
    def __init__(self):
        self.profile = 0

    def get(self, url, **kw):
        if "structura2015.mp" in url and "pag=0" not in url:
            self.profile += 1
        return super().get(url, **kw)


def test_continue_reia_de_la_individ(tmp_path, monkeypatch):
    # un scrape intrerupt: 2 membri n-au apucat sa fie luati. --continue ii
    # fetch-uieste doar pe ei; restul vin din run/membri. Lista se ia oricum.
    patch_pick_5_members(monkeypatch)
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    for f in sorted(Path("run/membri").glob("*.json"))[:2]:
        f.unlink()

    fetcher = _FetcherNumaraProfile()
    rez = ruleaza(fetcher, tmp_path, leg=2024, client=_ClientNumara(), mod="continue")
    assert fetcher.profile == 2
    assert sum(len(c["deputati"]) + len(c["senatori"]) for c in rez["circumscriptii"]) == 10
    assert R.incarca("run")["attempts"] == 2


def test_continue_retrimite_la_llm_doar_esuatii(tmp_path, monkeypatch):
    # stage 2 picat pentru 2 membri (batch 503) -> --continue ii trimite doar pe ei
    patch_pick_5_members(monkeypatch)
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    rec = R.incarca("run")
    uids = list(rec["membri"])[:2]
    for u in uids:
        R.marcheaza(rec, u, s2=False)
    R.salveaza("run", rec)

    cap = _ClientCaptura()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=cap, mod="continue")
    assert {m["id"] for m in cap.payloads} == set(uids)


def test_continue_fara_receipt_nu_face_nimic(tmp_path):
    rez = ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=None, mod="continue")
    assert rez == {"circumscriptii": [], "incomplet": []}


def test_all_forteaza_llm_si_nu_scrie_receipt(tmp_path, monkeypatch):
    patch_pick_5_members(monkeypatch)
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientNumara())
    c = _ClientNumara()
    ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=c, mod="all", run_dir="run_all")
    assert c.cereri == 1  # ignora cache-ul: toti din nou la LLM
    assert not Path("run_all/receipt.json").exists()


class _ClientPica:
    def rafineaza_batch(self, membri):
        raise RuntimeError("503 Service Unavailable")


def test_batch_esuat_iese_incomplet(tmp_path, monkeypatch):
    patch_pick_5_members(monkeypatch)
    rez = ruleaza(_FetcherFixture(), tmp_path, leg=2024, client=_ClientPica())
    assert len(rez["incomplet"]) == 10  # publicat mecanic, dar de reluat
    assert primul_deputat(tmp_path)["_rafinare"] is None


def test_fetch_lista_cdep_reincearca_pe_gol(monkeypatch):
    monkeypatch.setattr("scrapers.build._PAUZE_REFETCH", (0, 0))
    good = (FIXTURES / "cdep_par_c.html").read_text(errors="replace")

    class F:
        def __init__(self):
            self.n = 0

        def get(self, url, **kw):
            self.n += 1
            return _Resp("<html></html>") if self.n == 1 else _Resp(good)

    f = F()
    circ = build._fetch_lista_cdep(f, "http://x", robust=True)
    assert sum(len(c["deputati"]) for c in circ) > 0 and f.n == 2  # a reincercat
    f2 = F()
    circ2 = build._fetch_lista_cdep(f2, "http://x", robust=False)
    assert sum(len(c["deputati"]) for c in circ2) == 0 and f2.n == 1  # --all nu reincearca
