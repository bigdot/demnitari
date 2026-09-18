"""Assemble the final per-member records and validate the dataset.

Merging rules (one member = data from up to 4 sources):
  - lista par=C  -> short group name (PSD), official email (deputies),
                    social links, profil_url
  - profil       -> everything else (name split, party/group history,
                    photo, offices, cv_url)
  - cv (optional)          -> personal email + socials -> alte_contacte
  - bio senat.ro (optional) -> official @senat.ro email, phone, offices
The short group name from the list wins over the profile's long form
("PSD" vs "Grupul parlamentar al Partidului Social Democrat").
"""

from __future__ import annotations

import logging
import re
import time

log = logging.getLogger("demnitari.build")

# thresholds: legislature 2024-2028 has 331 deputies / 134 senators;
# anything far below means a broken scrape, not a real shrink
MIN_DEPUTATI = 250
MIN_SENATORI = 100

# escalating waits before refetching an invalid (rate-limited) profile page
_PAUZE_REFETCH = (10, 30)


import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


# party long name -> short form (2024-2028 legislature). Keyed by normalized
# (diacritics-insensitive) long name. Unknown parties fall back to their long
# form and the LLM can shorten them; add new ones here as they appear.
_ABREV_PARTID = {
    "partidul social democrat": "PSD",
    "partidul national liberal": "PNL",
    "uniunea salvati romania": "USR",
    "alianta pentru unirea romanilor": "AUR",
    "uniunea democrata maghiara din romania": "UDMR",
    "partidul oamenilor tineri": "POT",
    "partidul umanist social liberal": "PUSL",
    "partidul s.o.s. romania": "SOS",
    "s.o.s. romania": "SOS",
    "partidul miscarea populara": "PMP",
    "forta dreptei": "FD",
    "reper": "REPER",
}

# markers cdep puts in the party slot when a member has NO current party
_FARA_PARTID = ("fara adeziune", "grupul parlamentar", "deputati neafiliati",
                "senatori neafiliati", "neafiliat")


def _scurt_partid(nume: str | None) -> str | None:
    """Short form of a party name, or the name itself if unknown/None."""
    if not nume:
        return None
    return _ABREV_PARTID.get(_norm(nume), nume)


def _partid_curent(partid: str | None) -> str | None:
    """Current party long form, or None when it's a 'no party' marker."""
    if partid and any(m in _norm(partid) for m in _FARA_PARTID):
        return None
    return partid


def _partid_mandat(partide_precedente: dict, partid_curent):
    """Party the member was elected with = earliest entry in the party history
    (keys "YYYY-MM_YYYY-MM", sorted by start). Empty history means they never
    switched, so the current party is the one they won the seat with."""
    if partide_precedente:
        prima = min(partide_precedente, key=lambda k: k.split("_")[0])
        return partide_precedente[prima]
    return partid_curent


def _clasifica_link(url: str) -> str:
    for retea in ("facebook", "instagram", "linkedin", "youtube", "tiktok"):
        if retea in url:
            return retea
    if re.search(r"(x|twitter)\.com/", url):
        return "x"
    return "site"


def asambleaza_parlamentar(
    lista_entry: dict, profil: dict, cv: dict | None, bio: dict | None,
    cv_text: str = "",
) -> dict:
    # single contacts structure (mechanical baseline; the LLM cleans/enriches it)
    socials: list[dict] = []
    other_emails: list[str] = []
    numbers: list[str] = []
    website = None

    def _adauga_link(tip, url):
        nonlocal website
        if tip == "site":
            website = website or url
        else:
            socials.append({tip: url})

    for url in lista_entry.get("linkuri", []):
        _adauga_link(_clasifica_link(url), url)
    for cheie, valoare in (cv or {}).items():
        if cheie == "email":
            other_emails.append(valoare)
        else:
            _adauga_link(cheie, valoare)
    if bio and bio.get("telefon"):
        numbers.append(bio["telefon"])

    contacts = {
        "official_email": lista_entry.get("email") or (bio or {}).get("email"),
        "other_emails": other_emails,
        "offices": profil.get("birouri") or (bio or {}).get("birouri") or [],
        "numbers": numbers,
        "socials": socials,
        "website": website,
    }

    import json as _json

    from scrapers.llm import hash_text

    # idm is per-chamber (deputy idm=1 != senator idm=1), so the global cache
    # key is chamber + idm. cam=2 deputies, cam=1 senators (from the profil URL).
    cam_m = re.search(r"cam=(\d+)", lista_entry["profil_url"])
    uid = f"{cam_m.group(1) if cam_m else '?'}:{lista_entry['idm']}"

    # party the seat was won with = earliest entry in the party history (period
    # keys are "YYYY-MM_YYYY-MM"); if they never switched, it's the current one.
    mandat_long = _partid_mandat(profil["partide_precedente"], profil["partid"])
    partid_long = _partid_curent(profil["partid"])  # None on 'no party' markers
    # a member with no current party and no minority organization is an
    # independent de facto ("Indep." or "Fără adeziune" both mean no party)
    if partid_long is None and not profil.get("organizatie"):
        partid_long = "Indep."

    entity = {
        "uid": uid,
        "idm": lista_entry["idm"],
        "nume": profil["nume"],
        "prenume": profil["prenume"],
        "afiliat": profil["afiliat"],
        # afiliere: member is only *affiliated* to their group (not a full
        # member) — distinct from `afiliat` (has a group at all vs Neafiliat)
        "afiliere": "afiliat" if lista_entry.get("afiliat_grup") else None,
        # grup: short (from the list); grup_long: full name (from the profile)
        "grup": lista_entry.get("grup") or _scurt_partid(profil.get("grup_parlamentar")),
        "grup_long": profil.get("grup_parlamentar"),
        "grupuri_parlamentare_precedente": profil["grupuri_parlamentare_precedente"],
        # partid: short current; partid_long: full current; both None if they left
        "partid": _scurt_partid(partid_long),
        "partid_long": partid_long,
        "partid_mandat": _scurt_partid(mandat_long),  # short only, per UI
        "partide_precedente": profil["partide_precedente"],
        # minority organization (national-minority MPs; not a party)
        "organizatie": profil.get("organizatie"),
        "foto": profil["foto"],
        "profil_url": lista_entry["profil_url"],
        "cv_url": profil["cv_url"],
        "contacts": contacts,
    }
    # Cache key = checksum over the profile text AND the whole mechanical record
    # (structure + values). Computed pre-LLM, so it's deterministic from the
    # source. If the schema changes (a field added/renamed) or any mechanical
    # value changes, the hash changes -> cache miss -> re-correction, with no
    # need to manually delete the old JSON when the schema evolves.
    entity["profile_text_hash"] = hash_text(
        profil.get("text_profil", ""),
        cv_text,  # CV goes to the LLM now, so a CV-only change must re-refine
        _json.dumps(entity, sort_keys=True, ensure_ascii=False),
    )
    return entity


def valideaza(circumscriptii: list[dict]) -> None:
    """Fail loudly rather than publish partial/suspicious data."""
    if len(circumscriptii) != 43:
        raise ValueError(f"asteptam 43 de circumscriptii, avem {len(circumscriptii)}")
    deputati = sum(len(c["deputati"]) for c in circumscriptii)
    senatori = sum(len(c["senatori"]) for c in circumscriptii)
    if deputati < MIN_DEPUTATI:
        raise ValueError(f"prea putini deputati: {deputati} < {MIN_DEPUTATI}")
    if senatori < MIN_SENATORI:
        raise ValueError(f"prea putini senatori: {senatori} < {MIN_SENATORI}")
    for c in circumscriptii:
        if not c["deputati"] or not c["senatori"]:
            raise ValueError(f"circumscriptie goala: nr. {c['nr']} ({c['cod']})")


def scrie_json(circumscriptii: list[dict], out_dir, meta: dict) -> None:
    """Write parlamentari/<COD>.json + meta.json under out_dir."""
    import datetime
    import json
    from pathlib import Path

    out = Path(out_dir)
    (out / "parlamentari").mkdir(parents=True, exist_ok=True)
    for c in circumscriptii:
        continut = {
            "circumscriptie": {"cod": c["cod"], "nume": c["nume"], "nr": c["nr"]},
            "actualizat": datetime.date.today().isoformat(),
            "deputati": c["deputati"],
            "senatori": c["senatori"],
        }
        (out / "parlamentari" / f"{c['cod']}.json").write_text(
            json.dumps(continut, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    meta = {**meta, "actualizat": datetime.datetime.now().isoformat(timespec="seconds")}
    (out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )


LISTA_URL = "https://www.cdep.ro/ords/pls/parlam/structura2015.de?leg={leg}&par=C"
SENAT_LISTA_URL = "https://www.senat.ro/FisaSenatori.aspx"
SENAT_FISA_URL = "https://www.senat.ro/FisaSenator.aspx?ParlamentarID={guid}"


def _aplica_rafinare(entity: dict, rafinare: dict) -> None:
    """Merge the LLM-corrected fields onto the mechanical entity.

    The LLM corrects the whole record from the profile text: name (title
    stripped), group + affiliation, current party, and the contact section.
    Identity/structural fields (uid, idm, profil_url, foto) are never touched.
    """
    # LLM only refines when it returns a value (e.g. shortens an unmapped party);
    # the mechanical baseline already handles null-on-marker for partid.
    for cheie in ("nume", "prenume", "grup", "partid", "partid_mandat"):
        if rafinare.get(cheie):
            entity[cheie] = rafinare[cheie]
    if "afiliere" in rafinare:
        entity["afiliere"] = rafinare["afiliere"]

    # contacts: the LLM cleans/enriches the whole block from the office text +
    # CV — replace the mechanical baseline with the validated LLM version, but
    # keep the mechanical value for any sub-field the LLM left empty.
    if rafinare.get("contacts"):
        r = rafinare["contacts"]
        c = entity["contacts"]
        c["official_email"] = r.get("official_email") or c["official_email"]
        c["website"] = r.get("website") or c["website"]
        for cheie in ("other_emails", "offices", "numbers", "socials"):
            if r.get(cheie):
                c[cheie] = r[cheie]


BATCH_LLM = 50
# cap on the CV free text sent to the LLM — academic CVs can be huge, and the
# member's own contacts sit in the header/contact block near the top
CV_CAP = 5000
_CV_TRUNCHIAT = " […text CV trunchiat…]"


def _cap_cv(text: str) -> str:
    """Cap the CV text sent to the LLM, appending a marker when it was cut so
    the model knows it's a partial excerpt (not the whole CV)."""
    if len(text) > CV_CAP:
        return text[:CV_CAP] + _CV_TRUNCHIAT
    return text


def rafineaza_stage2(circumscriptii: list[dict], texte_dir, client,
                     precedent: dict | None, batch: int = BATCH_LLM) -> int:
    """Stage 2: LLM record correction, run after the mechanical scrape.

    Cache: a member whose profile_text_hash matches the previous publish
    reuses that entity's stored refinement (no LLM call) — nothing on the
    profile changed. The rest are sent to the LLM in batches of `batch`,
    reading their profile text from the tmp files stage 1 wrote. Returns the
    number of LLM requests made.

    NB: when the entity SCHEMA changes, the previously published JSON is
    incompatible — back it up and delete it so the scrape runs with no
    precedent (everyone re-corrected). The hash only tracks profile text, not
    schema, on purpose (daily operation only re-runs changed profiles).

    No client (no API key) leaves the mechanical result untouched. A failed
    batch leaves its members mechanical; since a failure is NOT cached as a
    hit, they are retried on the next build.
    """
    from pathlib import Path

    membri = [m for c in circumscriptii for m in c["deputati"] + c["senatori"]]
    precedent = precedent or {}
    de_rafinat = []
    for e in membri:
        prev = precedent.get(e["uid"])
        if prev and prev.get("profile_text_hash") == e["profile_text_hash"] \
                and prev.get("_rafinare") is not None:
            e["_rafinare"] = prev["_rafinare"]  # cache hit — profile unchanged
            _aplica_rafinare(e, e["_rafinare"])
        else:
            e["_rafinare"] = None
            de_rafinat.append(e)

    log.info("stage 2: %d din %d membri au nevoie de LLM (%d din cache)",
             len(de_rafinat), len(membri), len(membri) - len(de_rafinat))
    if client is None or not de_rafinat:
        return 0, set()

    # fields handed to the LLM as the mechanical record to correct — the full
    # record (short AND long forms), so it has complete context. No internal/
    # structural fields (uid, foto, hashes, profil_url stay ours).
    CAMPURI_RECORD = ("nume", "prenume", "grup", "grup_long", "afiliere",
                      "partid", "partid_long", "partid_mandat", "contacts")

    per_uid = {e["uid"]: e for e in de_rafinat}
    esuati: set[str] = set()  # uids whose batch failed (stage2 not done -> retry)
    cereri = 0
    for i in range(0, len(de_rafinat), batch):
        felie = de_rafinat[i:i + batch]
        payload = []
        for e in felie:
            slug = e["uid"].replace(":", "_")
            cale = Path(texte_dir) / f"{slug}.txt"
            text = cale.read_text(encoding="utf-8") if cale.exists() else ""
            cale_cv = Path(texte_dir) / f"{slug}.cv.txt"
            cv = cale_cv.read_text(encoding="utf-8") if cale_cv.exists() else ""
            record = {k: e[k] for k in CAMPURI_RECORD if k in e}
            payload.append({"id": e["uid"], "text": text, "cv": cv, "record": record})
        cereri += 1
        try:
            rezultat = client.rafineaza_batch(payload)
        except Exception as ex:
            log.warning("batch LLM %d-%d esuat (%s) — raman mecanici",
                        i, i + len(felie), ex)
            esuati.update(e["uid"] for e in felie)
            continue
        for uid, camp in rezultat.items():
            e = per_uid.get(uid)
            if e is not None and camp:
                e["_rafinare"] = camp
                _aplica_rafinare(e, camp)
        # members the LLM returned nothing for are clean — cache them as {} (not
        # None) so they're a cache HIT next run instead of churning every build
        for e in felie:
            if e["_rafinare"] is None:
                e["_rafinare"] = {}
        log.info("stage 2: batch %d/%d trimis", cereri,
                 (len(de_rafinat) + batch - 1) // batch)
    return cereri, esuati


def _membru_complet(fetcher, entry: dict, bio: dict | None, texte_dir=None,
                    logo_urls: dict | None = None) -> dict:
    from scrapers.cdep import cv_text, parse_cv, parse_profil

    profil = None
    ultima: Exception | None = None
    for pauza in (0, *_PAUZE_REFETCH):
        if pauza:
            log.warning("astept %ds inainte de refetch (rate limit?)", pauza)
            time.sleep(pauza)
        html = fetcher.get(entry["profil_url"]).text
        try:
            profil = parse_profil(html)
            break
        except ValueError as e:
            # ORDS rate-limits in bursts near the end of the build and
            # serves an HTTP-200 placeholder page; an instant refetch gets
            # the same thing, so back off properly before retrying
            ultima = e
            corp = " ".join(html.split())[:400]
            log.warning("profil invalid pentru %s (%s) — corp raspuns: %r",
                        entry["nume_complet"], e, corp)
    if profil is None:
        raise ultima
    cv = None
    cvt = ""
    if profil["cv_url"]:
        # the CV is optional enrichment; some CV pages 555 server-side
        # (e.g. Țepeluș, sept 2026) — log and publish the member without
        # a CV that day instead of aborting the whole build
        try:
            html_cv = fetcher.get(profil["cv_url"]).text
            cv = parse_cv(html_cv)
            cvt = _cap_cv(cv_text(html_cv))  # raw text for the LLM stage (capped)
        except Exception as e:
            log.warning("CV inaccesibil pentru %s (%s) — public fara CV",
                        entry["nume_complet"], e)
            profil["cv_url"] = None

    entity = asambleaza_parlamentar(entry, profil, cv, bio, cv_text=cvt)
    entity["_rafinare"] = None  # filled by stage 2 (rafineaza_stage2)

    # collect party/organization sigil URLs for the sigil manifest (built once
    # after the scrape); {formatiune -> cdep /aleg/ URL}
    if logo_urls is not None:
        logo_urls.update(profil.get("logo_formatiuni", {}))

    # park the full profile text in a tmp file for the batched LLM stage 2
    # (cleaned at end of scrape; also handy for debugging a bad extraction)
    if texte_dir is not None:
        from pathlib import Path

        slug = entity["uid"].replace(":", "_")
        (Path(texte_dir) / f"{slug}.txt").write_text(
            profil.get("text_profil", ""), encoding="utf-8")
        (Path(texte_dir) / f"{slug}.cv.txt").write_text(cvt, encoding="utf-8")
    return entity


# formations with a manufactured sigil bundled in scrapers/assets/ (no cdep
# logo). {formatiune -> filename}; copied into out/sigle/ during the build so
# the manifest reference is valid even on a fresh checkout (data is generated).
_SIGLE_MANUALE = {"Indep.": "indep.svg"}


def scrie_sigle(logo_urls: dict, out_dir, fetcher) -> int:
    """Download party/organization sigils into out_dir/sigle/ and write a
    manifest {formatiune -> path}. Cached: an already-present file isn't
    re-downloaded. Bundled manual sigils (Indep.) are added to the manifest."""
    import json
    import shutil
    from pathlib import Path

    out = Path(out_dir) / "sigle"
    out.mkdir(parents=True, exist_ok=True)
    # start from the existing manifest so a partial run (--continue re-scrapes
    # only some members, so logo_urls covers only those) adds to the full set
    # instead of clobbering it. Former-party sigils are worth keeping anyway.
    manifest: dict = {}
    vechi = out / "manifest.json"
    if vechi.exists():
        try:
            manifest = json.loads(vechi.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    # bundled manual sigils: copy the asset into out/sigle/ and list it
    assets = Path(__file__).parent / "assets"
    for nume, fname in _SIGLE_MANUALE.items():
        dst = out / fname
        if not dst.exists():
            shutil.copy(assets / fname, dst)
        manifest[nume] = f"sigle/{fname}"
    for nume, url in sorted(logo_urls.items()):
        fname = url.rsplit("/", 1)[-1]  # e.g. psd2016.jpg
        cale = out / fname
        if not cale.exists():
            try:
                cale.write_bytes(fetcher.get(url).content)
            except Exception as e:
                log.warning("sigla inaccesibila %s (%s)", url, e)
                continue
        manifest[nume] = f"sigle/{fname}"
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return len(manifest)


def _incarca_precedent(out_dir) -> dict:
    """Previously published entities keyed by idm — the LLM refinement cache."""
    import json
    from pathlib import Path

    precedent: dict = {}
    for f in (Path(out_dir) / "parlamentari").glob("*.json"):
        try:
            date = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for m in date.get("deputati", []) + date.get("senatori", []):
            if "uid" in m:
                precedent[m["uid"]] = m
    return precedent


def _fetch_lista_cdep(fetcher, url, robust: bool):
    """Fetch + parse a cdep chamber list. Under load cdep serves an HTTP-200
    placeholder that parses to zero members (an empty chamber is never real).
    The automated daily/continue run retries with backoff; `--all` is a manual
    force that fails fast — you just rerun it."""
    from scrapers.cdep import parse_lista

    circ = parse_lista(fetcher.get(url).text)
    if not robust:
        return circ
    for pauza in _PAUZE_REFETCH:
        if sum(len(c["deputati"]) for c in circ) > 0:
            return circ
        log.warning("lista cdep goala (%s) — astept %ds si reincerc", url, pauza)
        time.sleep(pauza)
        circ = parse_lista(fetcher.get(url).text)
    return circ


def ruleaza(fetcher, out_dir, leg: int = 2024, client="auto",
            mod: str = "daily", run_dir="run") -> dict:
    """Full build: fetch -> parse -> merge -> refine (LLM) -> validate -> write.

    `mod` controls the scope, tracked via a per-day receipt in run/:
      - "daily" (default): scrape everyone; stage2 uses the hash cache to skip
        members whose profile is unchanged. Writes a fresh receipt.
      - "continue": resume today's receipt — re-fetch and re-refine ONLY the
        members whose stages didn't pass (the rest are reused from the last
        published JSON, no fetch). Bumps `attempts`.
      - "all": force everyone through stage2 too (ignore the hash cache).

    Any failure (fetch, parse, mapping, validation) raises and aborts; the
    previously published JSONs stay live. Returns the run report.

    `client` is the LLM client for stage 2; "auto" builds one from the env
    if a key is present, None disables refinement (still a valid build).
    """
    import datetime
    import shutil
    import tempfile

    from scrapers import receipt as R
    from scrapers.circumscriptii import CIRCUMSCRIPTII
    from scrapers.mapare import mapeaza_senatori
    from scrapers.senat import (extract_postback_fields, parse_biografie,
                                parse_lista_senatori)

    if client == "auto":
        from scrapers.llm import LLMClient

        c = LLMClient()
        client = c if c.api_key else None
        log.info("stage 2 LLM: %s", "activ" if client else "dezactivat (fara API key)")

    azi = datetime.date.today().isoformat()
    base = _incarca_precedent(out_dir)  # last published entities, by uid

    if mod == "continue":
        rec = R.incarca(run_dir)
        if not rec or rec.get("data") != azi:
            log.warning("continue: fara receipt pentru azi (%s) — nimic de continuat", azi)
            return raport([])
        rec["attempts"] = rec.get("attempts", 1) + 1
        de_reluat = R.incompleti(rec)
        log.info("continue: attempt %d, %d membri de reluat", rec["attempts"], len(de_reluat))
    elif mod == "all":
        rec = None  # force-everything escape hatch — ignores + writes no receipt
        de_reluat = None
    else:  # daily
        rec = R.nou(azi)
        de_reluat = None  # None = do everyone

    # stage2 cache: "all" forces everyone; "continue" excludes the members it's
    # redoing (so they miss cache and get re-refined); "daily" uses the full cache
    if mod == "all":
        precedent = {}
    elif mod == "continue":
        precedent = {u: v for u, v in base.items() if u not in de_reluat}
    else:
        precedent = base

    texte_dir = tempfile.mkdtemp(prefix="demnitari_profil_")
    logo_urls: dict = {}  # {formatiune -> cdep sigil URL}, for the sigil manifest

    robust = mod != "all"  # daily/continue self-heal on empty lists; --all fails fast
    log.info("faza 1/4: listele")
    dep_lista = _fetch_lista_cdep(fetcher, LISTA_URL.format(leg=leg), robust)
    sen_lista = _fetch_lista_cdep(fetcher, LISTA_URL.format(leg=leg) + "&cam=1", robust)
    senat_ro = parse_lista_senatori(fetcher.get(SENAT_LISTA_URL).text)
    n_dep = sum(len(c["deputati"]) for c in dep_lista)
    n_sen = sum(len(c["deputati"]) for c in sen_lista)
    log.info("liste: %d deputati, %d senatori (cdep), %d senatori (senat.ro)",
             n_dep, n_sen, len(senat_ro))
    guid_pentru_idm = mapeaza_senatori(sen_lista, senat_ro)
    log.info("mapare senat.ro: %d/%d", len(guid_pentru_idm), n_sen)
    progres = {"facut": 0, "total": n_dep + n_sen}

    dep_de_circ = {c["nr"]: c["deputati"] for c in dep_lista}
    sen_de_circ = {c["nr"]: c["deputati"] for c in sen_lista}

    def _tick(nume_complet):
        progres["facut"] += 1
        if progres["facut"] % 25 == 0 or progres["facut"] == progres["total"]:
            log.info("membri: %d/%d (%s)", progres["facut"], progres["total"], nume_complet)

    def _uid_de(e):
        m = re.search(r"cam=(\d+)", e["profil_url"])
        return f"{m.group(1) if m else '?'}:{e['idm']}"

    def _reia(e):
        """On continue, reuse a done member from the last publish (no fetch)."""
        return mod == "continue" and _uid_de(e) not in de_reluat and _uid_de(e) in base

    log.info("faza 2/5: scrape mecanic (profiluri + CV-uri + biografii)")
    circumscriptii = []
    try:
        for circ in CIRCUMSCRIPTII:
            deputati = []
            for e in dep_de_circ.get(circ["nr"], []):
                if _reia(e):
                    deputati.append(base[_uid_de(e)])
                    continue
                try:
                    ent = _membru_complet(
                        fetcher, e, bio=None, texte_dir=texte_dir, logo_urls=logo_urls)
                except Exception:
                    log.error("esec la deputatul %s (%s)", e["nume_complet"], e["profil_url"])
                    raise
                deputati.append(ent)
                if rec is not None:
                    R.marcheaza(rec, ent["uid"], s1=True)
                _tick(e["nume_complet"])
            senatori = []
            for e in sen_de_circ.get(circ["nr"], []):
                if _reia(e):
                    senatori.append(base[_uid_de(e)])
                    continue
                try:
                    fisa_url = SENAT_FISA_URL.format(guid=guid_pentru_idm[e["idm"]])
                    fields = extract_postback_fields(fetcher.get(fisa_url).text)
                    bio = parse_biografie(fetcher.post(fisa_url, data=fields).text)
                    ent = _membru_complet(
                        fetcher, e, bio=bio, texte_dir=texte_dir, logo_urls=logo_urls)
                except Exception:
                    log.error("esec la senatorul %s (%s)", e["nume_complet"], e["profil_url"])
                    raise
                senatori.append(ent)
                if rec is not None:
                    R.marcheaza(rec, ent["uid"], s1=True)
                _tick(e["nume_complet"])
            circumscriptii.append({**circ, "deputati": deputati, "senatori": senatori})

        log.info("faza 3/5: rafinare LLM (batch)")
        cereri, esuati = rafineaza_stage2(circumscriptii, texte_dir, client, precedent)
        log.info("stage 2: %d cereri LLM (%d esuati)", cereri, len(esuati))
    finally:
        shutil.rmtree(texte_dir, ignore_errors=True)  # curata textele de profil

    # stage2 done for everyone whose batch didn't fail (cache hits + successes)
    if rec is not None:
        for m in (x for c in circumscriptii for x in c["deputati"] + c["senatori"]):
            R.marcheaza(rec, m["uid"], s2=(m["uid"] not in esuati))

    log.info("faza 4/5: validare")
    valideaza(circumscriptii)
    log.info("faza 5/5: scriere JSON + sigle in %s", out_dir)
    scrie_json(
        circumscriptii,
        out_dir,
        meta={
            "legislatura": leg,
            "deputati": sum(len(c["deputati"]) for c in circumscriptii),
            "senatori": sum(len(c["senatori"]) for c in circumscriptii),
        },
    )
    n_sigle = scrie_sigle(logo_urls, out_dir, fetcher)
    log.info("sigle: %d in manifest", n_sigle)

    if rec is not None:  # daily/continue track a receipt; --all does not
        R.salveaza(run_dir, rec)
        lipsa = R.incompleti(rec)
    else:
        lipsa = set(esuati)
    if lipsa:
        log.warning("INCOMPLET: %d membri fara stage1+stage2 (ruleaza `scrape --continue`)",
                    len(lipsa))
    else:
        log.info("COMPLET: toti membrii au trecut stage1+stage2")
    rap = raport(circumscriptii)
    rap["_incomplet"] = sorted(lipsa)  # __main__ turns this into the exit code
    return rap


def _acoperire(membri: list[dict]) -> dict:
    return {
        "total": len(membri),
        "email_oficial": sum(1 for m in membri if m["contacts"]["official_email"]),
        "birouri": sum(1 for m in membri if m["contacts"]["offices"]),
        "cv": sum(1 for m in membri if m["cv_url"]),
        "foto": sum(1 for m in membri if m["foto"]),
        "telefon": sum(1 for m in membri if m["contacts"]["numbers"]),
        "email_personal": sum(1 for m in membri if m["contacts"]["other_emails"]),
    }


def raport(circumscriptii: list[dict]) -> dict:
    return {
        "deputati": _acoperire([d for c in circumscriptii for d in c["deputati"]]),
        "senatori": _acoperire([s for c in circumscriptii for s in c["senatori"]]),
    }
