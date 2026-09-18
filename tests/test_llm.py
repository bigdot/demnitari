import json

import pytest

from scrapers.llm import LLMClient, hash_text, normalize_phone_number


@pytest.mark.parametrize("brut,asteptat", [
    ("0726.200.645", "+40726200645"),      # national cu puncte
    ("0726200645", "+40726200645"),        # national lipit
    ("0726 200 645", "+40726200645"),      # national cu spatii
    ("+40 723 257 640", "+40723257640"),   # international cu spatii
    ("+40723257640", "+40723257640"),      # deja canonic
    ("+ 40 723 257 640", "+40723257640"),  # plus rupt de spatiu
    ("(+40) 234588884", "+40234588884"),   # prefix in paranteze
    ("0040726200645", "+40726200645"),     # 00 in loc de +
    ("40723257640", "+40723257640"),       # fara + si fara 0
    ("0364 808 736", "+40364808736"),      # fix Cluj
])
def test_normalize_phone_number_la_international(brut, asteptat):
    assert normalize_phone_number(brut) == asteptat


def test_normalize_phone_number_lasa_neschimbat_ce_nu_recunoaste():
    # 9 cifre, nu e numar RO valid — nu fabricam un prefix
    assert normalize_phone_number("065275904") == "065275904"
    assert normalize_phone_number("") == ""


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
    assert r["numbers"] == ["+40364808736"]  # textul invalid respins + normalizat
    assert r["other_emails"] == ["oana@murariu.legal"]
    assert r["socials"] == [{"facebook": "fb.com/oana"}]  # {bad:5} respins
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


def test_telefon_invalid_e_respins():
    c = _client_cu_raspuns({"5": {"contacts": {"numbers": ["sunati la cabinet"]}}})
    r = c.rafineaza_batch([{"id": 5, "text": "t"}])["5"]["contacts"]
    assert r["numbers"] == []


def test_numerele_se_normalizeaza_si_se_deduplica():
    # acelasi numar in doua formatari -> un singur numar canonic
    c = _client_cu_raspuns(
        {"5": {"contacts": {"numbers": ["0726.200.645", "0726 200 645", "+40 723 257 640"]}}})
    r = c.rafineaza_batch([{"id": 5, "text": "t"}])["5"]["contacts"]
    assert r["numbers"] == ["+40726200645", "+40723257640"]


def test_email_fara_arond_respins():
    c = _client_cu_raspuns({"5": {"contacts": {"other_emails": ["contact punct ro"]}}})
    r = c.rafineaza_batch([{"id": 5, "text": "t"}])["5"]["contacts"]
    assert r["other_emails"] == []


def test_reincearca_la_eroare_tranzitorie(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    c = LLMClient(api_key="test")
    ok = '{"5": {"contacts": {"numbers": ["0364 808 736"]}}}'
    raspunsuri = [RuntimeError("503"), RuntimeError("503"),
                  {"choices": [{"message": {"content": ok}}]}]

    def fake_post(payload):
        r = raspunsuri.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    c._post = fake_post
    r = c.rafineaza_batch([{"id": 5, "text": "t"}])["5"]["contacts"]
    assert r["numbers"] == ["+40364808736"]


def test_renunta_dupa_toate_incercarile(monkeypatch):
    import pytest

    monkeypatch.setattr("time.sleep", lambda s: None)
    c = LLMClient(api_key="test")

    def mereu_pica(payload):
        raise RuntimeError("503")

    c._post = mereu_pica
    with pytest.raises(RuntimeError):
        c.rafineaza_batch([{"id": 5, "text": "t"}])


def test_roteste_modelul_la_429(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    c = LLMClient(models=["model-a", "model-b"], api_key="test")
    folosite = []

    def post(payload):
        folosite.append(payload["model"])
        if payload["model"] == "model-a":
            raise RuntimeError("429 Too Many Requests")
        return {"choices": [{"message": {"content": '{"5": {"contacts": {"numbers": ["0364 808 736"]}}}'}}]}

    c._post = post
    r = c.rafineaza_batch([{"id": 5, "text": "t", "record": {}}])
    assert r["5"]["contacts"]["numbers"] == ["+40364808736"]
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
    assert "text CV:" in trimis
    assert "TEXT_CV_UNIC" in trimis
    # instructiunea: ia doar contactele lui, nu ale altor institutii din CV
    assert "CV" in trimis and "institut" in trimis.lower()
