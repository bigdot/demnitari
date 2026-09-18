"""Parsers for senat.ro senator biography (extra contact data).

The senator page (FisaSenator.aspx?ParlamentarID=<guid>) is an ASP.NET
WebForms app: the left-hand tabs ("Biografie", ...) are __doPostBack links,
not URLs. Getting the biography takes two requests:

  1. GET  FisaSenator.aspx?ParlamentarID=<guid>   -> harvest hidden form
     fields (__VIEWSTATE, __EVENTVALIDATION, ...) with extract_postback_fields()
  2. POST the same URL with those fields plus
     __EVENTTARGET=ctl00$B_Center$Repeater14$ctl00$lnkBiog
     -> the response HTML contains the CV, parsed by parse_biografie()

The biography sections are label/value table pairs; the ones we need:
  "Contact în teritoriu"    -> local office addresses, one per line, each
                               prefixed with "- "
  "Coordonate de contact"   -> "e-mail:" and "telefon:" label/value rows
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

BIOGRAFIE_EVENTTARGET = "ctl00$B_Center$Repeater14$ctl00$lnkBiog"

_HIDDEN = ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION")
_TELEFON_RE = re.compile(r"(\+?40?\s?7\d{8}|0\d{9})")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def extract_postback_fields(html: str) -> dict[str, str]:
    """Hidden WebForms fields needed to replay the Biografie postback."""
    fields = {"__EVENTTARGET": BIOGRAFIE_EVENTTARGET, "__EVENTARGUMENT": ""}
    for name in _HIDDEN:
        m = re.search(r'id="%s" value="([^"]*)"' % name, html)
        if m:  # senat.ro has EventValidation disabled — omit absent fields
            fields[name] = m.group(1)
    return fields


def _linii_dupa_eticheta(soup: BeautifulSoup, eticheta: str, max_linii: int = 20) -> list[str]:
    """Visible text lines that follow a section label, up to the next label."""
    nod = soup.find(string=re.compile(re.escape(eticheta)))
    if not nod:
        return []
    linii = []
    for element in nod.find_parent("table").find_all_next(string=True):
        text = element.strip()
        if not text or text == eticheta:
            continue
        if element.find_parent("script") or element.find_parent("style"):
            break  # sections end where the page scripts begin
        linii.append(text)
        if len(linii) >= max_linii:
            break
    return linii


def parse_biografie(html: str) -> dict:
    """Contact data from the Biografie postback response."""
    soup = BeautifulSoup(html, "lxml")
    bio: dict = {"email": None, "telefon": None, "birouri": []}

    for linie in _linii_dupa_eticheta(soup, "Contact în teritoriu"):
        if linie.startswith("- "):
            bio["birouri"].append(linie[2:].strip())
        else:
            break  # first non-address line = next section

    for linie in _linii_dupa_eticheta(soup, "Coordonate de contact"):
        if bio["email"] is None:
            m = _EMAIL_RE.search(linie)
            if m:
                bio["email"] = m.group(0)
        if bio["telefon"] is None:
            m = _TELEFON_RE.search(linie)
            if m:
                bio["telefon"] = m.group(1)
        if bio["email"] and bio["telefon"]:
            break

    return bio


def parse_lista_senatori(html: str) -> list[dict]:
    """Senators from FisaSenatori.aspx: [{"guid": ..., "nume": ...}].

    The page repeats each senator card in several groupings (alphabetical,
    by group, ...), so dedup by GUID. Names render as "NUME Prenume".
    """
    vazuti: dict[str, str] = {}
    for m in re.finditer(
        r"FisaSenator\.aspx\?ParlamentarID=([0-9a-fA-F-]+)'>([^<]+)</a>", html
    ):
        vazuti.setdefault(m.group(1).lower(), m.group(2).strip())
    return [{"guid": g, "nume": n} for g, n in vazuti.items()]
