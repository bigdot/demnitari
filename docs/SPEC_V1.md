# Demnitari v1 — Design

**Status:** Implementat (v1)
**Data:** 2026-09-18
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

**Un singur repo public GitHub** (`demnitari`): scrapere + frontend + workflow.

Datele NU se versionează în v1. Un cron zilnic în Actions le regenerează la fiecare
rulare, le împachetează în artefactul de build și le publică direct pe GitHub Pages.
Fără repo de date, fără submodul, fără branch `gh-pages`. `site/data/` = director
generat (gitignored local + în CI). Istoricul componenței Parlamentului = re-scrape,
nu git log; scrape-ul e determinist, deci reproductibil.

```
CI (cron zilnic + dispatch manual), un singur job:
  localitati (SIRUTA) + scrape (cdep + senat.ro) ──> site/data/
    stage 1 mecanic (parse) ──> stage 2 LLM (Gemini: rafinează contactele)
  ──> vite build (copiază site/data în dist/data)
  ──> upload-pages-artifact ──> deploy-pages
  retry in-job (--continue, sleep 2 min, max 3) dacă un batch LLM pică (Gemini 503)
```

- Lookup-ul e: județ → un JSON per județ (lazy fetch client-side).
- Datele trăiesc doar în deploy-ul curent de pe Pages; nu se comit nicăieri.
  Deploy = `GITHUB_TOKEN` + `permissions: pages: write, id-token: write`. Fără token
  cross-repo (nu mai există repo de date).

## Pipeline în două etape

Parserul mecanic face tot ce e structurat (nume, grupuri, istoric partide, linkuri,
birouri). Dar secțiunea "Biroul parlamentar" + CV-ul sunt text liber pe care membrii
îl decorează cum vor (emoji, telefon/site amestecate în adrese). Regexurile nu prind
fiecare variantă, așa că textul ăla îl dăm unui LLM și validăm output-ul mecanic
(**modelul propune, codul verifică**).

- **Stage 1 (mecanic, determinist):** fetch + parse cdep/senat.ro → entitatea cu
  baseline de contacte. Zero rețea în teste (parserele-s funcții pure HTML→date).
- **Stage 2 (LLM, Gemini):** corectează recordul din textul profilului + textul CV:
  numele (scoate funcții strecurate), grup/afiliere, partidul curent, și secțiunea
  de contacte (separă birouri / telefoane / website, scoate emoji, ia din CV doar
  contactele proprii, nu ale altor instituții). Endpoint OpenAI-compatibil; rotație
  de modele la 429; batch de 50/prompt.
  - **Cache:** `profile_text_hash` = sha256 peste (text profil + text CV + recordul
    mecanic). Rafinarea rulează doar dacă hash-ul s-a schimbat față de publicarea
    precedentă. Membrii pe care LLM-ul nu-i schimbă primesc `_rafinare = {}` (nu
    `null`) → cache hit data viitoare, nu se re-trimit degeaba.
  - **Validare mecanică:** numele de familie nu se poate schimba; grupul doar din
    whitelist; partidul ≠ numele grupului; emailuri cu `@`; telefoanele normalizate
    la format internațional `+40...` + dedup.

## Date

### Surse (scrape zilnic)

- **cdep.ro** — ambele camere ("Parlamentul României"): liste pe circumscripții +
  profiluri + CV-uri, pentru deputați (`cam=2`) și senatori (`cam=1`). Doar `www.`
  (non-www dă 301). Sigla partidelor/organizațiilor din `/aleg/`.
- **senat.ro** — doar Biografia senatorilor (contact suplimentar: telefon, birouri).
- **data.gov.ro** — nomenclatorul SIRUTA (localitati.json).
- Circumscripții: 41 județe + București (42) + Diaspora (43).

### Output (`site/data/`)

- `meta.json` — legislatura, counts, data ultimului scrape.
- `localitati.json` — index autocomplete din SIRUTA (~13.7k intrări), cu forme fără
  diacritice precalculate + `rang` (TIP) pt ordonarea căutării. București: sectoare
  → circumscripția B. Diaspora: o intrare specială → DIA.
- `sigle/` — logo-urile descărcate (`sigle/<slug>.<ext>`) + `manifest.json`
  ({formatiune → cale}) + `indep.svg` (siglă manuală "Ind.", bundle din
  `scrapers/assets/`, copiată la build). Manifestul se face prin **merge** (dedupe
  pe nume), ca un `--continue` parțial să nu-l golească.
- `parlamentari/<COD>.json` — per circumscripție (`CJ.json`, `B.json`, `DIA.json`).
  Deputații și senatorii au ACEEAȘI schemă:
  ```json
  {
    "circumscriptie": {"cod": "CJ", "nume": "Cluj", "nr": 13},
    "actualizat": "2026-09-18",
    "deputati": [ <parlamentar> ],
    "senatori":  [ <parlamentar> ]
  }
  ```
  Schema `<parlamentar>`:
  ```json
  {
    "uid": "2:106",
    "idm": 106,
    "nume": "FIFOR",
    "prenume": "Mihai-Viorel",
    "afiliat": true,
    "afiliere": "afiliat | null",
    "grup": "PSD",
    "grup_long": "Grupul parlamentar al PSD",
    "grupuri_parlamentare_precedente": {"2024-12_2026-06": "SOS România"},
    "partid": "PSD | Indep. | null",
    "partid_long": "Partidul Social Democrat | Indep. | null",
    "partid_mandat": "POT",
    "partide_precedente": {"2024-12_2025-05": "Partidul Oamenilor Tineri"},
    "organizatie": "... | null (doar minorități, art. 62 Constituție)",
    "foto": "https://www.cdep.ro/parlamentari/l2024/....JPG",
    "profil_url": "https://www.cdep.ro/ords/pls/parlam/structura2015.mp?idm=...",
    "cv_url": "string | null (doar cine are CV publicat)",
    "contacts": {
      "official_email": "...@cdep.ro / ...@senat.ro | null",
      "other_emails": ["email personal din CV (@yahoo, @gmail...)"],
      "offices": ["adresele birourilor parlamentare din teritoriu"],
      "numbers": ["+40..."],
      "socials": [{"facebook": "url"}, {"instagram": "..."}],
      "website": "... | null"
    },
    "profile_text_hash": "sha256 — cheia de cache pt stage 2",
    "_rafinare": "{corecțiile LLM} | {} (curat) | null (nerafinat)"
  }
  ```
  Convenții:
  - `uid` = `"cam:idm"` (cam=2 deputați, cam=1 senatori); idm NU e unic global.
  - **Grup vs partid = dimensiuni distincte** (cineva poate fi în grupul PSD dar cu
    partidul PUSL). Forma scurtă (`grup`/`partid`) + lungă (`_long`).
  - `partid_mandat` = partidul cu care și-a câștigat mandatul (prima formațiune din
    istoric); afișat evidențiat când diferă de partidul curent (traseism).
  - Fără partid și fără organizație = independent → `partid = "Indep."`. Minoritarii
    au `organizatie` (nu partid).
  - Perioadele istoricului normalizate `YYYY-MM_YYYY-MM` ("iun. 2026" → "2026-06").
  - Câmpurile fără date rămân null / listă goală — nu inventăm.

### Surse per câmp (rezumat; detaliile de parsare = comentarii în cod)

  - **Lista pe circumscripții** (`structura2015.de?leg=...&par=C[&cam=1]`, 1 req/cameră):
    gruparea pe circumscripții, nume, grup curent (+ marcaj afiliat), email @cdep.ro
    (deputați), linkuri sociale, profil_url.
  - **Profilul cdep.ro** (1 req/parlamentar): nume/prenume, partid + grup cu istoric
    și perioade, organizație (minoritari), foto, birouri, cv_url, siglele
    formațiunilor. `text_profil` = doar secțiunile relevante (nu toată pagina — fără
    activitate volatilă, altfel cache-ul se strică zilnic).
  - **CV-ul cdep.ro** (1 req/parlamentar cu CV): email personal + social mecanic;
    textul brut al CV-ului merge la stage 2 (telefoane/emailuri în plus).
  - **Biografia senat.ro** (2 req/senator: GET fișă + POST postback "Biografie"):
    email @senat.ro, telefon, birouri — doar senatori. Mapare cdep↔senat pe nume
    normalizat, validată 1:1 la build.

  Buget: ~1025 requesturi/rulare la ~1 req/sec ≈ 10–12 min. Snapshot-urile HTML brute
  NU se comit.

### Robustețe

- **Stage 1 sau validare eșuată** (fetch/parse rupt, sau date suspecte: < 250
  deputați, < 100 senatori, județ cu 0 parlamentari) → build-ul **eșuează**, nu se
  urcă artefact nou, deploy-ul precedent de pe Pages rămâne live. Nu se publică date
  parțiale mecanic.
- **Listă cdep goală** (placeholder HTTP 200 sub sarcină) → retry cu backoff la
  daily/continue; `--all` eșuează rapid (îl re-rulezi manual).
- **Stage 2 parțial** (un batch Gemini 503) → membrii picați rămân cu baseline
  mecanic (tot valid) și se publică; retry-ul in-job (`--continue`) îi reia. Un eșec
  NU se cache-uiește, deci se re-încearcă.
- Receipt (`run/receipt.json`, efemer) urmărește per membru stage1/stage2 pentru
  reluare; exit code 2 = publicat dar incomplet.

## Componente

### 1. Scrapere (`scrapers/`, Python, uv + pyproject)

- `cdep.py`, `senat.py`, `mapare.py` — fetch + parse (requests + BeautifulSoup/lxml).
- `llm.py` — stage 2 (client OpenAI-compatibil, prompt, validare, normalizare telefon).
- `build.py` — orchestrare: stage 1 + stage 2 + validare + scriere JSON + sigle.
- `localitati.py` — SIRUTA → localitati.json.
- Moduri (`python -m scrapers [--continue|--all]`, expuse prin `just scrape`):
  - **daily** (default) — scrape tot, cache pe stage 2, receipt proaspăt.
  - **--continue** — reia doar incompleții din receipt (restul refolosiți din
    publicarea anterioară, fără fetch); rapid.
  - **--all** — forțează tot prin stage 2 (ignoră cache); nu atinge receipt-ul.

### 2. Frontend (`site/`, Svelte 5 + Vite, fără SvelteKit, fără router)

- Un ecran, un box de căutare cu autocomplete pe localități (insensibil la diacritice;
  caută pe `localitati.json`, încărcat la start). La selecție: fetch
  `parlamentari/<COD>.json` al județului → carduri Deputați, apoi Senatori.
- Card: nume + foto, siglele (curentă color + fostele partide alb-negru), grup,
  partid (+ mandat evidențiat la traseiști / "independent" / organizație la minoritari),
  birouri, **Email** (oficial + celelalte, mailto:), telefoane (tel:), linkuri
  (website + social), link spre profilul oficial.
- Date încărcate prin `fetch` de JSON static (nu bundle-uit); `base: './'` pt Pages
  sub `/demnitari/`. Selecția în URL hash (`#55268` = SIRUTA), shareable.
- Română, mobile-first, fără librării de UI; CSS de mână.

### 3. CI (`.github/workflows/deploy.yml`)

- Cron zilnic (ora ~06:00 RO) + `workflow_dispatch`. Un singur job:
  checkout → setup uv + node → localitati + scrape (cu retry in-job) → vite build →
  upload-pages-artifact → deploy-pages.
- Secret: `GEMINI_API_KEY`. Permisiuni: `pages: write`, `id-token: write`. Fără
  token cross-repo, fără submodul.

## Testare

- pytest pe parsere + build cu fixtures HTML locale (fără rețea în teste).
- Validarea regulilor de robustețe (counts, județe goale) + validarea output-ului LLM.
- Frontend: smoke — build-ul trece.
