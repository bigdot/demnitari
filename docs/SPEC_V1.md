# Demnitari v1 — Design

**Status:** Draft spre aprobare
**Data:** 2026-09-16
**Scope v1:** site static: bagi localitatea într-un box cu autocomplete, primești
numele și datele de contact ale parlamentarilor circumscripției tale (deputați +
senatori). Atât — fără alte texte, note sau explicații în UI.

## Problema

Un cetățean nu știe cine îl reprezintă în Parlament. Site-ul răspunde la:
"stau în <localitate> — cine sunt deputații și senatorii mei și cum îi contactez?"

Nota electorală (context, NU apare în UI): din 2016 parlamentarii se aleg pe liste
la nivel de județ — circumscripția = județul, pentru ambele camere. Nu există
"deputatul unei adrese"; răspunsul corect pentru orice adresă e lista completă a
circumscripției. Localitatea servește doar la aflarea județului.

## Arhitectura

Totul e static în două repo-uri publice GitHub:

- **`demnitari`** (aplicația): scrapere + frontend + workflows. Zero JSON-uri de
  date comise aici. `site/data/` = git submodule spre repo-ul de date.
- **`demnitari-data`** (datele): doar JSON-urile generate. Storage pasiv, fără
  workflows. Istoricul componenței Parlamentului = git log-ul acestui repo.

```
demnitari (cron zilnic în Actions):
  scrapere ──> scriu în site/data (submodulul) ──> commit+push în demnitari-data
                                                └──> bump pointer submodul (commit în demnitari)
                                                └──> build Vite + deploy GitHub Pages
```

- Lookup-ul e: județ → un JSON per județ.
- Ciclul rulează integral la fiecare scrape reușit (meta.json se schimbă zilnic),
  deci bump zilnic — care ține automat și scheduled workflows active.


## Date

### Surse (scrape zilnic)

- **cdep.ro** — ambele camere (platforma "Parlamentul României"): liste pe
  circumscripții + profiluri + CV-uri, pentru deputați (`cam=2`) și senatori (`cam=1`).
- **senat.ro** — doar Biografia senatorilor (contact suplimentar: telefon, birouri).
- Circumscripții: 41 județe + București (42) + Diaspora (43).

### Output (`site/data/`)

- `meta.json` — data ultimului scrape reușit per sursă, legislatura, counts.
- `localitati.json` — index pentru autocomplete, din nomenclatorul SIRUTA
  (dataset public): `[{"nume": "Turda", "judet": "CJ", "siruta": 55268}, ...]`,
  ~13k intrări, plus forme fără diacritice precalculate pentru căutare.
  București: sectoarele apar ca intrări (toate duc la circumscripția B).
  Diaspora: o intrare specială ("Diaspora / în afara țării" → DIA).
- `parlamentari/<COD>.json` — per circumscripție (ex: `CJ.json`, `B.json`, `DIA.json`).
  Deputații și senatorii au ACEEAȘI schemă:
  ```json
  {
    "circumscriptie": {"cod": "CJ", "nume": "Cluj", "nr": 13},
    "actualizat": "2026-09-16",
    "deputati": [ <parlamentar> ],
    "senatori":  [ <parlamentar> ]
  }
  ```
  Schema `<parlamentar>`:
  ```json
  {
    "nume": "FIFOR",
    "prenume": "Mihai-Viorel",
    "afiliat": true,
    "grup_parlamentar": "PSD",
    "grupuri_parlamentare_precedente": {"2024-12_2026-06": "SOS România"},
    "partid": "Partidul Social Democrat",
    "partide_precedente": {"2024-12_2026-06": "Partidul S.O.S. România"},
    "foto": "https://www.cdep.ro/parlamentari/l2024/....JPG",
    "profil_url": "https://www.cdep.ro/ords/pls/parlam/structura2015.mp?idm=...",
    "cv_url": "string | null (doar cine are CV publicat)",
    "contact_parlamentar": {
      "email": "...@cdep.ro sau ...@senat.ro | null",
      "birou": ["adresele birourilor parlamentare din teritoriu"]
    },
    "alte_contacte": {
      "telefon": "... | absent",
      "email": "email personal din CV | absent",
      "facebook": "... | absent",
      "site": "... | absent"
    }
  }
  ```
  Convenții: perioadele istoricului normalizate `YYYY-MM_YYYY-MM` (luna românească
  "iun. 2026" → "2026-06"); `afiliat` = grupul curent nu e "Neafiliați"; câmpurile
  fără date rămân null / absente — nu inventăm date.

### Surse per câmp (rezumat; detaliile de parsare = comentarii în cod)

  Ambele camere au liste + profiluri pe cdep.ro (`cam=2` deputați, `cam=1` senatori):
  - **Lista pe circumscripții** (`structura2015.de?leg=...&par=C[&cam=1]`, 1 req/cameră):
    gruparea pe circumscripții, nume, grup curent, email @cdep.ro (doar deputați),
    linkuri sociale, profil_url.
  - **Profilul cdep.ro** (1 req/parlamentar): nume/prenume (majuscule = nume de
    familie), partid + grup cu istoric și perioade, foto, birouri (deputați),
    cv_url (butonul CV apare doar la cine are CV).
  - **CV-ul cdep.ro** (1 req/parlamentar cu CV): email personal + alte contacte.
  - **Biografia senat.ro** (2 req/senator: GET fișă + POST postback "Biografie"):
    email @senat.ro, telefon, "Contact în teritoriu" (birouri) — doar senatori.
    Maparea cdep.ro ↔ senat.ro se face pe nume normalizat, validată 1:1 la build.

  Buget total: ~1000 requesturi/zi la 1 req/sec ≈ 17 min de CI.
- Snapshot-urile HTML brute NU se comit în v1 (zgomot); doar JSON-urile derivate.

### Reguli de robustețe

- Dacă un scraper eșuează sau scoate date suspecte (ex: < 250 deputați total,
  < 100 senatori, un județ cu 0 parlamentari), build-ul **eșuează** și JSON-urile
  vechi rămân publicate. Nu se publică niciodată date parțiale.
- `meta.json` + un banner discret în UI arată data ultimei actualizări.

## Componente

### 1. Scrapere (`scrapers/`, Python, uv + pyproject ca la mrvote)

- `cdep.py`, `senat.py` — fetch + parse (requests + BeautifulSoup/lxml), întorc
  liste de dataclass-uri `Parlamentar`.
- `build.py` — orchestrare: rulează ambele, validează (regulile de mai sus),
  scrie JSON-urile în `site/data/`.
- Parserele sunt funcții pure HTML→date; fetch-ul e separat (testabil offline).

### 2. Frontend (`site/`, Svelte + Vite, fără SvelteKit, fără router)

- Un ecran, un singur element: box de căutare cu autocomplete pe localități
  (insensibil la diacritice — "iasi" găsește "Iași"; caută pe `localitati.json`,
  încărcat la start). La selecție: fetch `parlamentari/<COD>.json` al județului
  → carduri Deputați, apoi Senatori.
- Card: nume, partid/grup, email (mailto:), link spre profilul oficial, foto dacă e.
- Fără alte texte/note/explicații în UI; doar data actualizării, discret în footer.
- Română, mobile-first, fără librării de UI; CSS de mână.
- Selecția se reflectă în URL hash (`#55268` = SIRUTA) — link-urile se pot da mai
  departe și repun starea la load.

### 3. CI (`.github/workflows/`, în repo-ul `demnitari`)

- `scrape.yml` — cron zilnic (ora ~06:00 RO) + manual dispatch:
  1. checkout cu `submodules: true`;
  2. rulează `build.py` (scrie în `site/data/`);
  3. commit + push în `demnitari-data` (auth: deploy key SSH cu write, secret în
     repo-ul `demnitari`), apoi commit de bump al pointerului de submodul în
     `demnitari`. Rulează la FIECARE scrape reușit — meta.json (last scrape date)
     se schimbă zilnic oricum. Mesajul de commit distinge refresh de schimbare
     reală: `data: 2026-09-16 (no changes)` / `data: 2026-09-16 (changed: CJ, B)`;
  4. apelează job-ul de deploy direct (workflow_call), NU prin trigger de push —
     push-urile făcute cu GITHUB_TOKEN nu declanșează alte workflows (gotcha
     GitHub cunoscut).
- `deploy.yml` — workflow_call (de la scrape) + push pe main (modificări de cod):
  checkout cu submodules, vite build, upload pe GitHub Pages
  (actions/deploy-pages, fără branch gh-pages).
- Deploy-ul folosește pointerul de submodul (pinned) — reproducibil: orice commit
  din `demnitari` identifică exact datele cu care s-a publicat.

## Testare

- pytest pe parsere cu fixtures HTML salvate local (fără rețea în teste).
- Testul de validare a regulilor de robustețe (counts, județe goale).
- Frontend: smoke minimal — build-ul trece și JSON-urile de fixture se randează
  (nu investim în test harness de UI pentru un ecran).

