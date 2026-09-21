import json

from scrapers.llm import LLMClient, hash_text

# NB: telefoanele nu se valideaza/normalizeaza aici — LLM-ul doar le propune;
# E.164 + validarea se fac intr-un singur loc, la final (tests/test_telefoane.py)


def test_hash_stabil_si_sensibil():
    assert hash_text("a", "b") == hash_text("a", "b")
    assert hash_text("a", "b") != hash_text("a", "c")
    # separatorul previne coliziuni intre concatenari diferite
    assert hash_text("ab", "c") != hash_text("a", "bc")


def _client_cu_raspuns(obj) -> LLMClient:
    c = LLMClient(api_key="test")
    c._post = lambda payload: {"choices": [{"message": {"content": json.dumps(obj)}}]}
    return c


def test_batch_curata_si_valideaza_pe_id():
    c = _client_cu_raspuns(
        {
            "213": {
                "contacts": {
                    "official_email": None,
                    "other_emails": ["oana@murariu.legal"],
                    "offices": ["  Cluj-Napoca, Str. X nr. 1  ", "", "Huedin, Str. Y"],
                    "numbers": ["0364 808 736", "text invalid"],
                    "socials": [{"facebook": "fb.com/oana"}, {"bad": 5}],
                    "website": "oanamurariu.ro",
                }
            }
        }
    )
    r = c.rafineaza_batch([{"id": 213, "text": "t", "record": {}}])["213"]["contacts"]
    assert r["offices"] == ["Cluj-Napoca, Str. X nr. 1", "Huedin, Str. Y"]  # gol scos
    assert r["numbers"] == ["0364 808 736", "text invalid"]  # validarea e la final
    assert r["other_emails"] == ["oana@murariu.legal"]
    assert r["socials"] == [{"facebook": "https://fb.com/oana"}]  # {bad:5} respins
    assert r["website"] == "https://oanamurariu.ro"  # protocol adaugat


def test_corecteaza_nume_grup_afiliere_partid():
    c = _client_cu_raspuns({
        "2:115": {
            "nume": "GAVRILESCU", "prenume": "Graţiela Leocadia",
            "grup": "PSD", "afiliere": "afiliat", "partid": "PUSL",
        }
    })
    r = c.rafineaza_batch([{"id": "2:115", "text": "t",
                            "record": {"nume": "GAVRILESCU"}}])["2:115"]
    assert r["grup"] == "PSD"
    assert r["afiliere"] == "afiliat"
    assert r["partid"] == "PUSL"


def test_partid_null_nu_e_stocat():
    # partid=null de la LLM nu se stocheaza — mecanicul gestioneaza null-ul
    c = _client_cu_raspuns({"2:114": {"partid": None}})
    r = c.rafineaza_batch([{"id": "2:114", "text": "t", "record": {}}])["2:114"]
    assert "partid" not in r


def test_llm_scurteaza_partid_mandat():
    # baseline mecanic vine forma lunga; LLM-ul o scurteaza la abreviere
    c = _client_cu_raspuns({"2:114": {"partid_mandat": "POT"}})
    r = c.rafineaza_batch([{"id": "2:114", "text": "t",
        "record": {"partid_mandat": "Partidul Oamenilor Tineri"}}])["2:114"]
    assert r["partid_mandat"] == "POT"


def test_partid_nu_poate_fi_numele_grupului():
    # guardrail: LLM-ul nu poate pune grupul ca partid (Teslariu: grup PNL)
    c = _client_cu_raspuns({"2:300": {"partid": "PNL"}})
    r = c.rafineaza_batch([{"id": "2:300", "text": "t",
                            "record": {"grup": "PNL"}}])["2:300"]
    assert "partid" not in r


def test_numele_de_familie_halucinat_e_respins():
    # LLM-ul nu poate schimba numele de familie fata de recordul mecanic
    c = _client_cu_raspuns({"2:40": {"nume": "POPESCU", "prenume": "Simona"}})
    r = c.rafineaza_batch([{"id": "2:40", "text": "t",
                            "record": {"nume": "BUCURA-OPRESCU"}}])["2:40"]
    assert "nume" not in r  # respins: familia nu se potriveste


def test_grup_necunoscut_e_respins():
    c = _client_cu_raspuns({"5": {"grup": "Partidul Inventat"}})
    r = c.rafineaza_batch([{"id": 5, "text": "t", "record": {}}])["5"]
    assert "grup" not in r


def test_numere_non_string_sunt_respinse():
    c = _client_cu_raspuns({"5": {"contacts": {"numbers": ["0726 200 645", 5, None, "  "]}}})
    r = c.rafineaza_batch([{"id": 5, "text": "t"}])["5"]["contacts"]
    assert r["numbers"] == ["0726 200 645"]


def test_email_fara_arond_respins():
    c = _client_cu_raspuns({"5": {"contacts": {"other_emails": ["contact punct ro"]}}})
    r = c.rafineaza_batch([{"id": 5, "text": "t"}])["5"]["contacts"]
    assert r["other_emails"] == []


def test_emailurile_propuse_de_model_sunt_validate_pe_camera_membrului():
    # id-ul e uid-ul: "1:…" = senator -> singurul oficial admis e @senat.ro
    c = _client_cu_raspuns({"1:5": {"contacts": {
        "official_email": "psdsenat2016@gmail.com",
        "other_emails": ["ion.pop@senat.ro", "ion.pop@cdep.ro",
                         "https://www.tiktok.com/@ionpop"]}}})
    r = c.rafineaza_batch([{"id": "1:5", "text": "E-mail: Ion.Pop@senat.ro"}])["1:5"]["contacts"]
    assert r["official_email"] == "ion.pop@senat.ro"
    # gmail-ul nu e oficial; @cdep.ro la senator si URL-ul nu sunt admise deloc
    assert r["other_emails"] == ["psdsenat2016@gmail.com"]


def test_oficial_construit_de_model_din_nume_nu_e_admis():
    # cazul real (CI, 21.09): 65 de adrese prenume.nume@senat.ro / @cdep.ro care nu
    # apareau nicaieri in datele membrului
    c = _client_cu_raspuns({
        "1:13": {"contacts": {"official_email": "ilie-gavril.bolojan@senat.ro"}},
        "2:86": {"contacts": {"official_email": None,
                              "other_emails": ["andrei.csillag@cdep.ro", "csillag@yahoo.com"]}},
        "2:10": {"contacts": {"official_email": "lucian.andrusca@cdep.ro"}},
    })
    r = c.rafineaza_batch([
        {"id": "1:13", "text": "BOLOJAN Ilie-Gavril, senator", "record": {"nume": "BOLOJAN"}},
        {"id": "2:86", "text": "CSILLAG Andrei", "cv": "ANTET: E-mail csillag@yahoo.com"},
        # scrisa in datele CV-ului (alta capitalizare) -> admisa
        {"id": "2:10", "text": "ANDRUŞCĂ", "cv": "CONTACT [email: Lucian.andrusca@cdep.ro] CONTEXT: …"},
    ])
    assert r["1:13"]["contacts"]["official_email"] is None
    assert r["2:86"]["contacts"]["official_email"] is None  # nici strecurata prin other_emails
    assert r["2:86"]["contacts"]["other_emails"] == ["csillag@yahoo.com"]
    assert r["2:10"]["contacts"]["official_email"] == "lucian.andrusca@cdep.ro"


def test_eroare_tranzitorie_se_propaga_dintr_o_singura_incercare():
    # clientul nu doarme si nu reincearca: un 503 iese imediat, iar retry-ul cu
    # backoff il face workerul din build (nu tine pe loc celelalte batch-uri)
    import pytest

    c = LLMClient(api_key="test")
    apeluri = []

    def pica(payload):
        apeluri.append(1)
        raise RuntimeError("503 Service Unavailable")

    c._post = pica
    with pytest.raises(RuntimeError, match="503"):
        c.rafineaza_batch([{"id": 5, "text": "t"}])
    assert len(apeluri) == 1


def test_toate_modelele_pe_429_da_eroare():
    import pytest

    c = LLMClient(models=["model-a", "model-b"], api_key="test")

    def quota(payload):
        raise RuntimeError("429 Too Many Requests")

    c._post = quota
    with pytest.raises(RuntimeError, match="429"):
        c.rafineaza_batch([{"id": 5, "text": "t"}])


def test_roteste_modelul_la_429():
    c = LLMClient(models=["model-a", "model-b"], api_key="test")
    folosite = []

    def post(payload):
        folosite.append(payload["model"])
        if payload["model"] == "model-a":
            raise RuntimeError("429 Too Many Requests")
        return {"choices": [{"message": {"content": '{"5": {"contacts": {"numbers": ["0364 808 736"]}}}'}}]}

    c._post = post
    r = c.rafineaza_batch([{"id": 5, "text": "t", "record": {}}])
    assert r["5"]["contacts"]["numbers"] == ["0364 808 736"]
    assert "model-a" in folosite and "model-b" in folosite
    # dupa epuizarea lui a, ramane pe b pentru batch-urile urmatoare
    assert c.model == "model-b"


def test_promptul_include_toti_membrii_din_batch():
    c = LLMClient(api_key="test")
    captat = {}
    c._post = lambda payload: captat.update(payload) or {
        "choices": [{"message": {"content": "{}"}}]
    }
    c.rafineaza_batch([
        {"id": 213, "text": "TEXT_UNU", "birouri": ["MEC_UNU"]},
        {"id": 999, "text": "TEXT_DOI", "birouri": []},
    ])
    trimis = captat["messages"][0]["content"]
    assert "TEXT_UNU" in trimis and "TEXT_DOI" in trimis
    assert "213" in trimis and "999" in trimis


def test_promptul_include_cv_ul_si_instructiunea():
    c = LLMClient(api_key="test")
    captat = {}
    c._post = lambda payload: captat.update(payload) or {
        "choices": [{"message": {"content": "{}"}}]
    }
    c.rafineaza_batch([
        {"id": 213, "text": "PROFIL", "cv": "TEXT_CV_UNIC", "record": {}},
    ])
    trimis = captat["messages"][0]["content"]
    assert "date CV:" in trimis
    assert "TEXT_CV_UNIC" in trimis
    # promptul explica formatul extrasului din CV si ca modelul decide din context
    assert "ANTET:" in trimis and "CONTACT [" in trimis and "CONTEXT:" in trimis
    assert "institut" in trimis.lower()
