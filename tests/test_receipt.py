from scrapers import receipt as R


def test_nou_are_structura_de_baza():
    rec = R.nou("2026-09-18")
    assert rec == {"data": "2026-09-18", "attempts": 1, "membri": {}}


def test_salveaza_si_incarca_roundtrip(tmp_path):
    rec = R.nou("2026-09-18")
    R.marcheaza(rec, "2:106", s1=True, s2=True)
    R.salveaza(tmp_path, rec)
    assert R.incarca(tmp_path) == rec


def test_incarca_lipsa_da_none(tmp_path):
    assert R.incarca(tmp_path) is None


def test_salveaza_creeaza_directorul(tmp_path):
    # run/ poate lipsi — salveaza il face
    tinta = tmp_path / "nu" / "exista"
    R.salveaza(tinta, R.nou("2026-09-18"))
    assert (tinta / "receipt.json").exists()


def test_marcheaza_seteaza_doar_ce_i_dai():
    rec = R.nou("x")
    R.marcheaza(rec, "1:5", s1=True)
    assert rec["membri"]["1:5"] == {"s1": True}
    R.marcheaza(rec, "1:5", s2=False)
    assert rec["membri"]["1:5"] == {"s1": True, "s2": False}


def test_incompleti_si_complet():
    rec = R.nou("x")
    R.marcheaza(rec, "a", s1=True, s2=True)
    R.marcheaza(rec, "b", s1=True, s2=False)   # stage2 picat
    R.marcheaza(rec, "c", s1=False, s2=False)  # deloc
    assert R.incompleti(rec) == {"b", "c"}
    assert not R.e_complet(rec)

    R.marcheaza(rec, "b", s2=True)
    R.marcheaza(rec, "c", s1=True, s2=True)
    assert R.incompleti(rec) == set()
    assert R.e_complet(rec)
