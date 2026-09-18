"""Parsers for cdep.ro (Parlamentul României) — both chambers.

The circumscription-grouped list lives at:
    https://www.cdep.ro/ords/pls/parlam/structura2015.de?leg=<an>&par=C          (deputati, cam=2)
    https://www.cdep.ro/ords/pls/parlam/structura2015.de?leg=<an>&par=C&cam=1    (senatori)

HTML layout (same for both chambers):
  - one <table> per group of rows; circumscription headers are rows like
        <tr><th colspan=4 bgcolor="#e0e0e0">Circumscriptia electorala nr. 1 -
            <a href=".../structura2015.ce?cir=1&leg=2024">ALBA</a></th></tr>
    NB: the displayed number ("nr. 1") is authoritative; the `cir=` URL param
    is a different internal id (off by one for some counties) — never use it.
  - member rows follow their circumscription header:
        td[0] row number "1."
        td[1] <a href=".../structura2015.mp?idm=18&cam=2&leg=2024">Bara Nicolae-Adrian</a>
        td[2] <a href=".../structura2015.gp?idg=1&leg=2024">PSD<br></a>  (group, short name)
        td[3] contact cell: optional <a href="mailto:...">, optional external links.
              Data-quality quirk: external links are sometimes double-prefixed
              ("http://https://x.com/...") — strip the bogus leading "http://".
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE = "https://www.cdep.ro"

# Parliament of the 2024-2028 legislature was validated in December 2024.
# History entries without an explicit "din <luna> <an>" started with the mandate.
LEG_START = "2024-12"

_CIRC_RE = re.compile(r"Circumscriptia electorala nr\.\s*(\d+)\s*-")
_IDM_RE = re.compile(r"idm=(\d+)")

# Romanian month abbreviations as rendered on cdep.ro ("- din  iun. 2026")
_LUNI = {"ian": 1, "feb": 2, "mar": 3, "apr": 4, "mai": 5, "iun": 6,
         "iul": 7, "aug": 8, "sep": 9, "oct": 10, "noi": 11, "nov": 11, "dec": 12}
_DATA_RE = re.compile(r"(%s)\.?\s+(\d{4})" % "|".join(_LUNI))


def _clean_external(href: str) -> str:
    # fix "http://https://..." double-prefix typos from the source data
    return re.sub(r"^http://(?=https?://)", "", href.strip())


def parse_lista(html: str) -> list[dict]:
    """Parse the par=C list into circumscriptions with their members.

    Returns: [{"nr": 1, "nume": "ALBA", "deputati": [membru, ...]}, ...]
    ordered by circumscription number as rendered in the page.
    """
    soup = BeautifulSoup(html, "lxml")
    circumscriptii: list[dict] = []
    curenta: dict | None = None

    for tr in soup.find_all("tr"):
        th = tr.find("th", string=None)
        header_text = tr.get_text(" ", strip=True)
        m = _CIRC_RE.search(header_text) if th else None
        if m and tr.find("th"):
            nume_link = tr.find("a")
            curenta = {
                "nr": int(m.group(1)),
                "nume": nume_link.get_text(strip=True) if nume_link else "",
                "deputati": [],
            }
            circumscriptii.append(curenta)
            continue

        if curenta is None:
            continue
        profil = tr.find("a", href=_IDM_RE)
        if not profil:
            continue

        href = profil["href"]
        idm = int(_IDM_RE.search(href).group(1))

        # group cell: "<a>PSD<br> afiliat</a>" for members merely affiliated to
        # a group (not full members). Use a separator so the two aren't glued
        # into "PSDafiliat"; split the suffix into a flag.
        grup_link = tr.find("a", href=re.compile(r"structura2015\.gp\?"))
        grup = grup_link.get_text(" ", strip=True) if grup_link else None
        afiliat_grup = False
        if grup and grup.lower().endswith("afiliat"):
            grup = grup[: -len("afiliat")].strip()
            afiliat_grup = True

        email = None
        linkuri = []
        for a in tr.find_all("a", href=True):
            h = a["href"]
            if h.startswith("mailto:") and "webmaster" not in h:
                email = h.removeprefix("mailto:").strip()
            elif h.startswith("http") and "cdep.ro" not in h:
                linkuri.append(_clean_external(h))

        curenta["deputati"].append(
            {
                "idm": idm,
                "nume_complet": profil.get_text(strip=True),
                "grup": grup,
                "afiliat_grup": afiliat_grup,
                "email": email,
                "linkuri": linkuri,
                "profil_url": urljoin(BASE, href),
            }
        )

    return circumscriptii


def _data_ym(text: str) -> str | None:
    """'iun. 2026' -> '2026-06' (Romanian month abbreviations)."""
    m = _DATA_RE.search(text)
    if not m:
        return None
    return f"{m.group(2)}-{_LUNI[m.group(1)]:02d}"


def _istoric_din_sectiune(box) -> tuple[str | None, dict[str, str]]:
    """Parse one mp-info-box2025 history section (party or group).

    Entries are <td> cells holding <a>NAME</a> plus an optional annotation:
        " - până în  iun. 2026"          (ended -> goes to history)
        " - din  iun. 2026"              (current, started mid-legislature)
        " - membru până în  iun. 2026"   (group flavour of the same)
    Cells with roles (Vicelider etc.) have no <a> and are skipped.
    An entry without "până în" is the current one. History keys are
    "<start>_<end>" in YYYY-MM, start defaulting to LEG_START.
    """
    curent = None
    istoric: dict[str, str] = {}
    for td in box.find_all("td"):
        a = td.find("a", href=re.compile(r"structura2015\.(fp|gp)\?"))
        if not a:
            continue
        nume = a.get_text(" ", strip=True)
        anotare = td.get_text(" ", strip=True).replace(nume, "", 1)
        if "până în" in anotare:
            start = None
            if "din" in anotare.split("până în")[0]:
                start = _data_ym(anotare.split("până în")[0])
            end = _data_ym(anotare.split("până în")[1])
            istoric[f"{start or LEG_START}_{end}"] = nume
        else:
            curent = nume
    return curent, istoric


def _logo_formatiuni(soup) -> dict[str, str]:
    """{formation name -> /aleg/ logo URL} for every party (Formaţiunea
    politică) and minority organization (Organizaţia minorităţilor naţionale)
    row. Covers current AND former formations, so each has its sigil from the
    member's own profile — even parties no longer in Parliament."""
    logos: dict[str, str] = {}
    for titlu in ("formatiunea politica", "organiza"):
        box = _sectiune(soup, titlu)
        if box is None:
            continue
        for tr in box.find_all("tr"):
            a = tr.find("a", href=re.compile(r"structura2015\.fp\?"))
            img = tr.find("img", src=re.compile(r"^/aleg/"))
            if a and img:
                logos[a.get_text(" ", strip=True)] = urljoin(BASE, img["src"])
    return logos


def _sectiune(soup, titlu_prefix: str):
    """Find the mp-info-box2025 whose <h4> starts with the given prefix
    (diacritics-insensitive, e.g. 'formatiunea politica')."""
    import unicodedata

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", s)
        return "".join(c for c in s if not unicodedata.combining(c)).lower()

    for box in soup.find_all("div", class_="mp-info-box2025"):
        h4 = box.find("h4")
        if h4 and norm(h4.get_text(strip=True)).startswith(titlu_prefix):
            return box
    return None


def parse_profil(html: str) -> dict:
    """Parse a member profile page (same template for both chambers).

    Name comes from the mp-profile-name2025 element as "Prenume NUME" —
    the all-caps token(s) are the family name (unicode-aware: ADOMNICĂI).
    The CV button (pag=0 link) is rendered only for members with a
    published CV, so its absence means cv_url = None (no extra request).
    """
    soup = BeautifulSoup(html, "lxml")

    nume_el = soup.find(class_="mp-profile-name2025")
    if nume_el is None:
        # ORDS occasionally serves a 200 with an empty/error body; make it
        # a clear signal so the caller can refetch instead of AttributeError
        raise ValueError("profil fara element mp-profile-name2025 (raspuns invalid?)")
    # element format: "Prenume NUME<br>funcție" — the name is before the first
    # <br>; a function ("chestor/vicepreşedinte/secretar al Camerei...") follows
    # it. Drop the <br> and everything after so the function stays out of the name.
    br = nume_el.find("br")
    if br is not None:
        for sib in list(br.next_siblings):
            sib.extract()
        br.extract()
    nume_toks, prenume_toks = [], []
    for tok in nume_el.get_text(" ", strip=True).split():
        (nume_toks if tok.isupper() else prenume_toks).append(tok)

    partid, partide_prec = (None, {})
    box = _sectiune(soup, "formatiunea politica")
    if box:
        partid, partide_prec = _istoric_din_sectiune(box)

    # National-minority MPs have no "Formaţiunea politică" section; instead they
    # have "Organizaţia minorităţilor naţionale" naming their minority
    # organization (legally NOT a party — Constitution art. 62 — so it goes in
    # its own field, not `partid`).
    organizatie = None
    box_org = _sectiune(soup, "organiza")
    if box_org:
        a = box_org.find("a", href=re.compile(r"structura2015\.fp"))
        if a:
            organizatie = a.get_text(" ", strip=True)

    grup, grupuri_prec = (None, {})
    box = _sectiune(soup, "grupul parlamentar")
    if box:
        grup, grupuri_prec = _istoric_din_sectiune(box)

    foto_el = soup.find("img", src=re.compile(r"^/parlamentari/"))

    circ_m = re.search(r"circumscrip\w*\s+electoral\w*\s+nr\.?\s*(\d+)",
                       soup.get_text(" ", strip=True), re.IGNORECASE)

    cv_link = soup.find("a", href=re.compile(r"idm=\d+[^\"]*pag=0"))

    # Office addresses as raw lines. No emoji/phone/site untangling here —
    # members format this section however they like (see Oana Murariu). The
    # LLM refinement stage (stage 2) cleans and splits contacts out of it.
    birouri = []
    box = _sectiune(soup, "biroul parlamentar")
    if box:
        for linie in box.get_text("\n", strip=True).split("\n"):
            linie = linie.strip().rstrip(";").strip()
            if linie and "@" not in linie and not linie.lower().startswith("biroul parlamentar"):
                birouri.append(linie)

    import unicodedata
    grup_norm = "".join(c for c in unicodedata.normalize("NFKD", grup or "")
                        if not unicodedata.combining(c)).lower()

    # LLM context: ONLY the relevant sections, not the whole page. Feeding the
    # full profile (committees, friendship groups, activity counters, ...) added
    # noise that made the LLM inconsistent run-to-run. A small, focused, stable
    # context -> deterministic output, and a stable profile_text_hash.
    parti = []
    name_box = soup.find(class_="mp-profile-name2025")
    if name_box:
        parti.append(name_box.get_text(" ", strip=True))
    detalii = soup.find(class_="mp-profile-details2025")
    if detalii:
        parti.append(detalii.get_text(" ", strip=True))
    for titlu in ("formatiunea politica", "organiza", "grupul parlamentar",
                  "biroul parlamentar"):
        box = _sectiune(soup, titlu)
        if box is not None:
            parti.append(box.get_text("\n", strip=True))
    text_profil = re.sub(r"\n{2,}", "\n", "\n".join(parti))

    return {
        "nume": " ".join(nume_toks),
        "prenume": " ".join(prenume_toks),
        "partid": partid,
        "partide_precedente": partide_prec,
        "organizatie": organizatie,  # minority organization (not a party)
        "grup_parlamentar": grup,
        "grupuri_parlamentare_precedente": grupuri_prec,
        "afiliat": bool(grup) and "neafilia" not in grup_norm,
        "foto": urljoin(BASE, foto_el["src"]) if foto_el else None,
        "circumscriptie_nr": int(circ_m.group(1)) if circ_m else None,
        "cv_url": urljoin(BASE, cv_link["href"]) if cv_link else None,
        "birouri": birouri,
        "text_profil": text_profil,
        "logo_formatiuni": _logo_formatiuni(soup),  # {formatiune -> logo URL}
    }


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_SOCIAL = {
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/"),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/"),
    "x": re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/"),
}


def _cv_soup(html: str) -> BeautifulSoup:
    """CV page with the site chrome stripped (header/footer/social bars carry
    the institution's own links on every page — not the member's contacts)."""
    soup = BeautifulSoup(html, "lxml")
    for el in soup.find_all(["header", "footer", "nav", "script", "style"]):
        el.decompose()
    for el in soup.find_all(class_=re.compile(r"footer|header2025|social")):
        el.decompose()
    return soup


def cv_text(html: str) -> str:
    """Cleaned free text of a CV page, handed to the LLM in stage 2 so it can
    pull phones / extra emails our mechanical parse_cv doesn't extract."""
    return _cv_soup(html).get_text(" ", strip=True)


def parse_cv(html: str) -> dict:
    """Extract personal contacts from a member CV page (pag=0).

    Two CV formats exist: the new Europass table (class cveuro2025) and a
    legacy free-form layout ("E-mail: x@y.com" lines, some with a PDF link).
    Instead of parsing each format, strip the site chrome (header, footer,
    social bars — which carry the institution's own facebook/twitter links
    on every page) and regex the remaining content for emails and socials.
    Official @cdep.ro / @senat.ro addresses are contact_parlamentar, not
    "alte_contacte", so they are excluded here.
    """
    soup = _cv_soup(html)

    contacte: dict[str, str] = {}

    text = soup.get_text(" ", strip=True)
    for email in _EMAIL_RE.findall(text):
        if not email.lower().endswith(("@cdep.ro", "@senat.ro")):
            contacte["email"] = email
            break

    for a in soup.find_all("a", href=True):
        href = _clean_external(a["href"])
        for retea, pat in _SOCIAL.items():
            if retea not in contacte and pat.match(href):
                contacte[retea] = href

    return contacte
