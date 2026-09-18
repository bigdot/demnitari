import json

import pytest

from scrapers.fetch import Fetcher
from scrapers.build import scrie_json


class _FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetcher_face_pauza_intre_requesturi(monkeypatch):
    pauze = []
    monkeypatch.setattr("time.sleep", lambda s: pauze.append(s))
    f = Fetcher(delay=1.0)
    f._session_get = lambda url, **kw: _FakeResponse()
    f.get("https://example.com/1")
    f.get("https://example.com/2")
    assert pauze  # a dormit intre cele doua


def test_fetcher_reincearca_la_eroare(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    raspunsuri = [_FakeResponse(500), _FakeResponse(500), _FakeResponse(200, "gata")]
    f = Fetcher(delay=0)
    f._session_get = lambda url, **kw: raspunsuri.pop(0)
    assert f.get("https://example.com").text == "gata"


def test_fetcher_renunta_dupa_3_incercari(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    f = Fetcher(delay=0)
    f._session_get = lambda url, **kw: _FakeResponse(500)
    with pytest.raises(RuntimeError):
        f.get("https://example.com")


def test_scrie_json(tmp_path):
    circ = {
        "nr": 13, "cod": "CJ", "nume": "Cluj",
        "deputati": [{"nume": "X"}], "senatori": [{"nume": "Y"}],
    }
    scrie_json([circ], tmp_path, meta={"legislatura": 2024})
    cj = json.loads((tmp_path / "parlamentari" / "CJ.json").read_text())
    assert cj["circumscriptie"] == {"cod": "CJ", "nume": "Cluj", "nr": 13}
    assert cj["deputati"] == [{"nume": "X"}]
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["legislatura"] == 2024
    assert "actualizat" in meta
