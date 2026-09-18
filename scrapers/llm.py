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
import os
import re
import time

import requests

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

_TELEFON_RE = re.compile(r"^[0-9 .()+-]{9,20}$")


def normalize_phone_number(brut: str) -> str:
    """Canonicalize a Romanian phone number to international form (+40...).

    The LLM emits the same number with inconsistent spacing/dots/plus between
    runs (`0726.200.645`, `0726200645`, `+40 723 257 640`), which would churn
    the UI and defeat dedup. Strip to digits and map RO national/00/+40 forms
    to `+40XXXXXXXXX`. Anything we can't confidently map is returned unchanged
    (we never fabricate a country code onto a number of the wrong length).
    """
    if not brut:
        return brut
    cifre = re.sub(r"\D", "", brut)
    if cifre.startswith("0040"):       # 0040 7xx... -> +40 7xx...
        cifre = cifre[2:]
    if cifre.startswith("40") and len(cifre) == 11:   # 40 + 9 cifre nationale
        return "+" + cifre
    if cifre.startswith("0") and len(cifre) == 10:    # 0 + 9 cifre nationale
        return "+40" + cifre[1:]
    return brut.strip()

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
    "official_email": "<email oficial @cdep.ro/@senat.ro sau null>",
    "other_emails": ["<email personal non-institutional (@yahoo, @gmail...)>"],
    "offices": ["<adresa unui birou parlamentar teritorial, text curat, fara emoji>"],
    "numbers": ["<numar de telefon de contact, doar cifre si separatori>"],
    "socials": [{"facebook": "<url/handle>"}, {"instagram": "..."}, {"x": "..."}],
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
            bloc += f"\ntext CV:\n{m['cv']}"
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
        "CV: unii au si un 'text CV' — o sursa secundara. Ia din CV DOAR contactele "
        "proprii ale parlamentarului (telefon, email, website personal). NU amesteca "
        "contactele altor institutii, universitati, laboratoare, firme sau persoane "
        "care apar in CV (angajatori, co-autori) — acelea NU sunt contactele lui. "
        "Daca textul CV se termina cu '[…text CV trunchiat…]', a fost taiat si vezi "
        "doar un fragment — nu presupune ca lipseste ce nu apare.\n"
        "Scoate emoji din toate campurile. Include un id doar daca ai corectat ceva.\n\n"
        f"Parlamentari:\n{corp}\n\n"
        "Raspunde doar cu obiectul JSON keyed by id."
    )


def _valideaza(brut: dict, record: dict | None = None) -> dict:
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
        oe = c.get("official_email")
        contacts["official_email"] = oe.strip() if isinstance(oe, str) and "@" in oe else None

        contacts["other_emails"] = [
            e.strip() for e in (c.get("other_emails") or [])
            if isinstance(e, str) and "@" in e
        ]
        contacts["offices"] = [
            o.strip() for o in (c.get("offices") or []) if isinstance(o, str) and o.strip()
        ]
        numere: list[str] = []
        for n in (c.get("numbers") or []):
            if isinstance(n, str) and _TELEFON_RE.match(n.strip()):
                canonic = normalize_phone_number(n.strip())
                if canonic not in numere:  # dedup (same number, diff formatting)
                    numere.append(canonic)
        contacts["numbers"] = numere
        socials = []
        for s in (c.get("socials") or []):
            if isinstance(s, dict):
                for retea, val in s.items():
                    if isinstance(val, str) and val.strip():
                        socials.append({retea: val.strip()})
        contacts["socials"] = socials

        site = c.get("website")
        if isinstance(site, str) and site.strip():
            contacts["website"] = site.strip() if site.startswith("http") else "https://" + site.strip()
        else:
            contacts["website"] = None

        out["contacts"] = contacts
    return out


def _e_rate_limit(e: Exception) -> bool:
    return "429" in str(e) or "Too Many Requests" in str(e)


class LLMClient:
    def __init__(self, models: list[str] | None = None, endpoint: str = ENDPOINT,
                 api_key: str | None = None, retries: int = 3):
        self.models = list(models) if models else list(MODELS)
        self.endpoint = endpoint
        self.api_key = api_key or os.environ.get(API_KEY_ENV, "")
        self.retries = retries
        self._i = 0  # current model index; advances when one is quota-exhausted

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
        returned. On transient errors (503) retries with backoff; on 429
        (quota exhausted) rotates to the next model and stays there.
        """
        record_pentru = {str(m["id"]): m.get("record", {}) for m in membri}
        continut = _prompt_batch(membri)
        ultima: Exception | None = None
        # try each remaining model; within a model, retry transient errors
        while self._i < len(self.models):
            for incercare in range(self.retries):
                try:
                    data = self._post({
                        "model": self.models[self._i],
                        "messages": [{"role": "user", "content": continut}],
                        "response_format": {"type": "json_object"},
                        "temperature": 0,
                    })
                    brut = json.loads(data["choices"][0]["message"]["content"])
                    return {
                        str(idm): _valideaza(camp, record_pentru.get(str(idm)))
                        for idm, camp in brut.items()
                        if isinstance(camp, dict)
                    }
                except Exception as e:
                    ultima = e
                    if _e_rate_limit(e):
                        break  # quota out for this model — rotate, don't retry it
                    if incercare < self.retries - 1:
                        time.sleep(2**incercare)
            if not _e_rate_limit(ultima):
                break  # non-quota failure — give up (caller keeps mechanical)
            self._i += 1  # next model
        raise ultima
