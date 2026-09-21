"""Stage 2: LLM refinement of the free-text contact section.

The mechanical parser handles everything structured (name, groups, party
history, links). But the "Biroul parlamentar" section is free text that
members decorate however they like — emoji, phone numbers and personal
sites mixed into address lines (see Oana Murariu). Regexes can't chase
every variant, so we hand that section to an LLM and validate its output
mechanically (the model proposes, the code verifies).

Provider-agnostic: any OpenAI-compatible chat endpoint works. Default is
Google Gemini's compatibility endpoint; override via env for CI or a
different provider. The model id must be current — Google retires old
ids (gemini-2.5-flash is gone; use gemini-3.6-flash as of 2026-09).

Caching: the caller passes each member's profile_text_hash. Refinement
only runs when the hash changed since the last build, so steady-state
LLM usage is ~zero.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading

import requests

from scrapers import emailuri, linkuri

log =logging.getLogger("demnitari.llm")

ENDPOINT = os.environ.get(
    "LLM_ENDPOINT",
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
)
# Each Gemini model id has its OWN free-tier daily quota, so we rotate through
# a list: when one returns 429 (quota exhausted), advance to the next. A full
# cold-start (~10 batches) fits one model; rotation only matters when a day's
# quota is already spent (e.g. repeated dev reruns). Override with LLM_MODELS
# (comma-separated) or the single LLM_MODEL.
MODELS = [m.strip() for m in os.environ.get(
    "LLM_MODELS",
    os.environ.get("LLM_MODEL",
                   "gemini-flash-lite-latest,gemini-3.5-flash-lite,"
                   "gemini-3.1-flash-lite,gemini-3.8-flash")
).split(",") if m.strip()]
API_KEY_ENV = os.environ.get("LLM_API_KEY_ENV", "GEMINI_API_KEY")

# known parliamentary groups (2024-2028) — the LLM's grup must be one of these
GRUPURI = {"PSD", "AUR", "PNL", "USR", "UDMR", "UPR", "POT", "SOS RO",
           "Minorități", "Minoritati", "Neafiliați", "Neafiliati"}

SCHEMA = """{
  "nume": "<numele de familie, DOAR familia, fara functii sau titluri>",
  "prenume": "<prenumele, fara functii/titluri de tip 'chestor al Camerei'>",
  "grup": "<forma scurta: PSD, AUR, PNL, USR, UDMR, UPR, POT, SOS RO, Minoritati, Neafiliati>",
  "afiliere": "<'afiliat' daca e doar afiliat la grup, nu membru plin; altfel null>",
  "partid": "<partidul CURENT, forma scurta (PSD, POT, PUSL...); null daca a plecat din partid si nu a intrat in altul (slotul de partid arata un nume de GRUP)>",
  "partid_mandat": "<partidul cu care si-a castigat mandatul, forma scurta — recordul are deja o valoare, scurteaz-o la abreviere (Partidul Oamenilor Tineri -> POT)>",
  "contacts": {
    "official_email": "<email oficial: @cdep.ro pentru deputat (id 2:…), @senat.ro pentru senator (id 1:…); altfel null>",
    "other_emails": ["<email personal non-institutional (@yahoo, @gmail...)>"],
    "offices": ["<adresa unui birou parlamentar teritorial, text curat, fara emoji>"],
    "numbers": ["<numar de telefon de contact, doar cifre si separatori>"],
    "socials": [{"facebook": "<URL complet al profilului, nu nume/handle>"}, {"instagram": "..."}, {"x": "..."}],
    "website": "<URL-ul site-ului personal sau null>"
  }
}"""


def hash_text(*parti: str) -> str:
    """Stable hash of a member's raw text (profile + CV + bio), the cache key."""
    h = hashlib.sha256()
    for p in parti:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _prompt_batch(membri: list[dict]) -> str:
    """Prompt for a batch of members: each has id + mechanical record + full
    profile text. The model corrects the record; returns JSON keyed by id."""
    blocuri = []
    for m in membri:
        bloc = (
            f"### id: {m['id']}\n"
            f"record mecanic: {json.dumps(m.get('record', {}), ensure_ascii=False)}\n"
            f"text profil:\n{m['text']}"
        )
        if m.get("cv"):
            bloc += f"\ndate CV:\n{m['cv']}"
        blocuri.append(bloc)
    corp = "\n\n".join(blocuri)
    return (
        "Esti un asistent de curatare a datelor pentru un site civic despre "
        "parlamentarii Romaniei. Pentru fiecare id ai un 'record mecanic' produs de "
        "un parser (poate avea erori: functia amestecata in nume, grupul lipit cu "
        "'afiliat', partidul vechi in loc de cel curent, emoji in contacte) si "
        "'text profil' = textul integral al paginii oficiale, care e SURSA DE ADEVAR.\n\n"
        "Corecteaza recordul folosind textul. Intoarce DOAR un obiect JSON keyed by "
        "id, fiecare valoare fiind un obiect cu structura (pune null unde nu exista):\n\n"
        f"{SCHEMA}\n\n"
        "Reguli: nu inventa nimic; foloseste doar informatia din record si text. "
        "Numele de familie NU il schimba (doar scoate functii/titluri strecurate). "
        "Grupul si partidul sunt DISTINCTE (cineva poate fi in grupul PSD dar cu "
        "partidul PUSL). Foloseste forma scurta pentru partid (PSD, POT, PUSL...).\n"
        "PARTID: 'partid' = partidul CURENT; daca in istoricul 'Formaţiunea politică' "
        "ultima intrare e un nume de GRUP (incepe cu 'Grupul parlamentar') sau "
        "'Fără adeziune', persoana a plecat din partid si nu a intrat in altul -> "
        "partid=null. NU pune numele grupului parlamentar ca partid. 'partid_mandat' "
        "vine deja completat in record — doar scurteaza-l la abreviere (forma scurta).\n"
        "AFILIERE: campul 'grup' din record poate veni lipit cu marcajul "
        "'afiliat' (ex: 'PSDafiliat', 'PSD afiliat') sau recordul poate avea deja "
        "afiliere='afiliat'. In ambele cazuri desparte/pastreaza: grup='PSD' si "
        "afiliere='afiliat'. Un membru afiliat NU e membru plin al grupului.\n"
        "CONTACTE: uita-te dupa adrese de birouri distincte, numere de telefon si "
        "website. E posibil sa fie multiple. Pune-le in campurile potrivite conform "
        "structurii (offices / numbers / website), nu le amesteca.\n"
        "CV: unii au si 'date CV' — o sursa secundara, din care iei DOAR contactele "
        "proprii ale parlamentarului. NU e textul intreg al CV-ului, ci un extras "
        "facut de un parser, cu formatul:\n"
        "  ANTET: <inceputul CV-ului, textual — nume, adresa, de obicei contactele lui>\n"
        "  CONTACT [<tip>: <valoare>; ...] CONTEXT: …<textul din CV din jurul valorii>…\n"
        "Fiecare linie CONTACT e un email / telefon / url gasit undeva in restul "
        "CV-ului; parserul NU stie al cui e. Tu decizi din CONTEXT: il adaugi doar "
        "daca reiese ca e al parlamentarului (ex: 'blog personal www.x.ro', 'Editor "
        "al blogului www.x.ro', 'E-mail personal'). NU il adaugi daca e al unui "
        "angajator, firma, institutie, universitate, liceu, conferinta, publicatie, "
        "proiect sau al altei persoane (ex: 'Universitatea Y, Site de internet "
        "www.y.ro', 'Numele angajatorului … www.firma.com', un profesor dat ca "
        "referinta, un link de articol/DOI). Un 'telefon' care in context e de fapt "
        "o data sau un numar de act il ignori. Daca din context nu e clar al cui e, "
        "NU il adaugi.\n"
        "Scoate emoji din toate campurile.\n"
        "RASPUNS: pentru FIECARE id primit, fara exceptie, intoarce obiectul COMPLET, "
        "cu toate campurile din structura, completate cu ce ai gasit in record + text "
        "profil + date CV. Nu exista raspuns gol: chiar daca recordul era deja corect, "
        "il rescrii intreg.\n\n"
        f"Parlamentari:\n{corp}\n\n"
        "Raspunde doar cu obiectul JSON keyed by id, cu toate id-urile."
    )


def _valideaza(brut: dict, record: dict | None = None, uid: str | None = None) -> dict:
    """Keep only well-formed values — the model proposes, we verify.

    `record` is the mechanical record; used to guard the surname (the LLM may
    strip a title but must not invent a different family name).
    """
    record = record or {}
    out: dict = {}

    # name: accept only if the surname is unchanged (guard against hallucination)
    nume = brut.get("nume")
    prenume = brut.get("prenume")
    if isinstance(nume, str) and nume.strip():
        if not record.get("nume") or nume.strip().upper() == str(record["nume"]).upper():
            out["nume"] = nume.strip()
            if isinstance(prenume, str) and prenume.strip():
                out["prenume"] = prenume.strip()

    # group: only accept a known short group name
    grup = brut.get("grup")
    if isinstance(grup, str) and grup.strip() in GRUPURI:
        out["grup"] = grup.strip()

    if brut.get("afiliere") == "afiliat":
        out["afiliere"] = "afiliat"

    # partid: never accept the group name as the party (group-as-party confusion)
    partid = brut.get("partid")
    if isinstance(partid, str) and partid.strip():
        partid = partid.strip()
        if not (record.get("grup") and partid == record["grup"]):
            out["partid"] = partid
    partid_mandat = brut.get("partid_mandat")
    if isinstance(partid_mandat, str) and partid_mandat.strip():
        out["partid_mandat"] = partid_mandat.strip()

    c = brut.get("contacts")
    if isinstance(c, dict):
        contacts: dict = {}
        # emailuri: fiecare adresa propusa de model e validata inainte sa intre
        # intr-un camp (oficial = doar domeniul camerei membrului)
        altele = c.get("other_emails") if isinstance(c.get("other_emails"), list) else []
        contacts["official_email"], contacts["other_emails"] = emailuri.admite(
            [c.get("official_email"), *altele], uid, cine=record.get("nume", ""))
        contacts["offices"] = [
            o.strip() for o in (c.get("offices") or []) if isinstance(o, str) and o.strip()
        ]
        # numerele raman cum le-a propus modelul; validarea + E164 se fac intr-un
        # singur loc, la finalul build-ului (telefoane.normalizeaza)
        contacts["numbers"] = [
            n.strip() for n in (c.get("numbers") or [])
            if isinstance(n, str) and n.strip()
        ]
        # linkuri: parsate — ce nu e URL se scoate, un "website" care e de fapt
        # profil de retea sociala trece la socials, fiecare retea dupa host
        contacts["website"] = c.get("website")
        contacts["socials"] = c.get("socials") if isinstance(c.get("socials"), list) else []
        linkuri.normalizeaza(contacts, cine=record.get("nume", ""))

        out["contacts"] = contacts
    return out


def _e_rate_limit(e: Exception) -> bool:
    return "429" in str(e) or "Too Many Requests" in str(e)


class LLMClient:
    def __init__(self, models: list[str] | None = None, endpoint: str = ENDPOINT,
                 api_key: str | None = None):
        self.models = list(models) if models else list(MODELS)
        self.endpoint = endpoint
        self.api_key = api_key or os.environ.get(API_KEY_ENV, "")
        self._i = 0  # current model index; advances when one is quota-exhausted
        self._lock = threading.Lock()  # main loop + retry worker share the client

    @property
    def model(self) -> str:
        return self.models[min(self._i, len(self.models) - 1)]

    # seam for tests
    def _post(self, payload: dict) -> dict:
        resp = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    def rafineaza_batch(self, membri: list[dict]) -> dict[str, dict]:
        """Correct a batch of member records in one request.

        `membri`: [{"id": <uid>, "record": <mechanical record>, "text": <profile text>}].
        Returns {str(id): validated corrected fields} — only ids the model
        returned. ONE attempt, no sleeping: a transient error (503) raises and
        the caller retries it off the main loop (build's retry worker). Only a
        429 (quota exhausted) is handled here, by rotating to the next model.
        """
        record_pentru = {str(m["id"]): m.get("record", {}) for m in membri}
        continut = _prompt_batch(membri)
        while True:
            i = self._i
            if i >= len(self.models):
                raise RuntimeError("429: toate modelele si-au epuizat quota")
            try:
                data = self._post({
                    "model": self.models[i],
                    "messages": [{"role": "user", "content": continut}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                })
            except Exception as e:
                if not _e_rate_limit(e):
                    raise
                with self._lock:  # rotate once even if both threads hit the 429
                    if self._i == i:
                        self._i += 1
                continue
            brut = json.loads(data["choices"][0]["message"]["content"])
            return {
                str(idm): _valideaza(camp, record_pentru.get(str(idm)), uid=str(idm))
                for idm, camp in brut.items()
                if isinstance(camp, dict)
            }
