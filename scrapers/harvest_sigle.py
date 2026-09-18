"""Standalone: harvest party sigils from cdep profiles into site/data/sigle/.

For every party a member has ever been in (current AND former), the logo is in
that member's own 'Formaţiunea politică' section — so even parties no longer in
Parliament have a sigil somewhere. This scans all published members' profiles,
downloads each unique party logo, and writes a manifest {party name -> path}.

Run manually for now to build the frontend:
    uv run python -m scrapers.harvest_sigle
Folded into the daily scrape later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from scrapers.cdep import _sectiune
from scrapers.fetch import Fetcher

DATA = Path("site/data")
OUT = DATA / "sigle"

# formations with no cdep logo but a manufactured sigil bundled in the repo
# (e.g. MPs elected as independents). The files are committed; not downloaded.
MANUAL = {"Indep.": "sigle/indep.svg"}


def logo_formatiuni(html: str) -> dict[str, str]:
    """{name -> /aleg/ logo URL} for every party (Formaţiunea politică) AND
    minority organization (Organizaţia minorităţilor naţionale) row."""
    soup = BeautifulSoup(html, "lxml")
    logos: dict[str, str] = {}
    for titlu in ("formatiunea politica", "organiza"):
        box = _sectiune(soup, titlu)
        if box is None:
            continue
        for tr in box.find_all("tr"):
            a = tr.find("a", href=re.compile(r"structura2015\.fp\?"))
            img = tr.find("img", src=re.compile(r"^/aleg/"))
            if a and img:
                src = img["src"]
                logos[a.get_text(" ", strip=True)] = (
                    src if src.startswith("http") else "https://www.cdep.ro" + src
                )
    return logos


def main() -> None:
    fetcher = Fetcher()

    # every party a member has been in (current + former), and one profile that
    # contains it — we only need ONE member per party, not all 464 profiles.
    nevoie: set[str] = set()
    profil_pentru: dict[str, str] = {}
    for f in (DATA / "parlamentari").glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        for m in d["deputati"] + d["senatori"]:
            partide = list((m.get("partide_precedente") or {}).values())
            if m.get("partid_long"):
                partide.append(m["partid_long"])
            if m.get("organizatie"):  # minority organizations
                partide.append(m["organizatie"])
            for p in partide:
                nevoie.add(p)
                profil_pentru.setdefault(p, m["profil_url"])

    # minimal set of profiles that covers every party (one per party; a
    # traseist's profile covers several, so the union is small)
    urls = sorted(set(profil_pentru.values()))
    print(f"{len(nevoie)} partide, {len(urls)} profiluri de fetchuit")

    partid_logo: dict[str, str] = {}
    for i, url in enumerate(urls, 1):
        for nume, logo in logo_formatiuni(fetcher.get(url).text).items():
            partid_logo.setdefault(nume, logo)
        print(f"  {i}/{len(urls)} — {len(partid_logo)}/{len(nevoie)} sigle")
        if nevoie <= partid_logo.keys():
            break  # avem toate

    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for nume in sorted(nevoie):
        if nume in MANUAL:  # manufactured sigil (already in repo)
            manifest[nume] = MANUAL[nume]
            print(f"  {nume} -> {MANUAL[nume]} (fabricat)")
            continue
        logo = partid_logo.get(nume)
        if not logo:
            print(f"  FARA SIGLA: {nume}")  # markers like 'Fără adeziune...'
            continue
        fname = logo.rsplit("/", 1)[-1]  # e.g. psd2016.jpg
        (OUT / fname).write_bytes(fetcher.get(logo).content)
        manifest[nume] = f"sigle/{fname}"
        print(f"  {nume} -> {fname}")

    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"ok: {len(manifest)}/{len(nevoie)} sigle in {OUT}")


if __name__ == "__main__":
    main()
