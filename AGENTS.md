# AGENTS.md

Ghid pentru agenți care lucrează în acest repo. Design-ul complet: `docs/SPEC_V1.md`.

**Limba de comunicare: romgleza** — română casual cu loanword-urile englezești
păstrate ca-atare (zi "box-ul", "commit", "deploy", nu le traduce forțat).

## Ce e

**demnitari** — site civic: bagi localitatea într-un box, primești parlamentarii
circumscripției tale (deputați + senatori) cu date de contact. Atât.

Site static (Svelte + Vite) + scrapere Python + un workflow GitHub Actions care
scrapează zilnic și publică pe GitHub Pages. **Un singur repo**; datele NU se
versionează — se regenerează la fiecare rulare și se împachetează în deploy.

## Layout

- `scrapers/` — Python (uv + pyproject). `cdep.py`/`senat.py`/`mapare.py` (fetch +
  parse), `llm.py` (rafinare LLM stage 2), `build.py` (orchestrare), `receipt.py`
  (state de rulare), `localitati.py` (SIRUTA), `fetch.py`, `assets/indep.svg`.
- `site/` — frontend Svelte 5 (runes) + Vite, fără SvelteKit. `src/App.svelte`,
  `Card.svelte`, `SearchBox.svelte`.
- `tests/` — pytest cu fixtures HTML locale (fără rețea). `fixtures/`.
- `site/data/` — **generat** (gitignored). Nu-l comite.

## Comenzi

```sh
just scrape              # scrape zilnic (stage 1 mecanic + stage 2 LLM) -> site/data
just scrape --continue   # reia doar membrii incompleți din run/receipt.json
just scrape --all        # forțează tot prin LLM (ignoră cache-ul)
just fetch-addresses     # regenerează site/data/localitati.json (SIRUTA)
just serve               # dev server Vite (cd site && npm run dev)
just test                # testele (pytest, rapide, offline)
cd site && npm run build # build de producție -> dist/ (copiază și site/data)
```

`GEMINI_API_KEY` vine din mediu (local: `~/.profile`; CI: secret). **Nu printa
secrete.** Fără cheie, build-ul merge fără stage 2 (doar mecanic).

## Pipeline în două etape

- **Stage 1 mecanic** (determinist): parse cdep/senat → entitatea cu contacte.
  Parserele-s funcții pure HTML→date; fetch-ul e separat (testabil offline).
- **Stage 2 LLM** (Gemini): rafinează contactele + nume/grup/partid din textul
  profilului + CV. **Modelul propune, codul verifică** — tot output-ul LLM e
  validat mecanic (`_valideaza`). Cache pe `profile_text_hash`; rulează doar la
  schimbare.

Principiu: dacă LLM-ul greșește, **fixezi contextul** (curatezi ce-i dai / completezi
recordul), NU scoți responsabilități din prompt.

## Convenții & gotchas

- **cdep.ro doar cu `www.`** (non-www dă 301).
- `uid = "cam:idm"` (cam=2 deputați, cam=1 senatori); `idm` NU e unic global.
- **Grup ≠ partid** (dimensiuni distincte). Fără partid → `partid="Indep."`;
  minoritarii au `organizatie`, nu partid. `partid_mandat` = partidul cu care a
  fost ales.
- `contacts` = un singur obiect: `official_email`, `other_emails[]`, `offices[]`,
  `numbers[]` (format `+40...`), `socials[]`, `website`.
- `text_profil` = doar secțiunile relevante (fără activitate volatilă — altfel
  cache-ul se strică zilnic).
- `_rafinare`: `{corecții}` / `{}` (curat, dar cache-abil) / `null` (nerafinat).
- Receipt (`run/receipt.json`, efemer): stage1/stage2 per membru; `--continue` îl
  citește. Exit code 2 = publicat dar incomplet.
- Editează cu Edit/Write, nu cu `sed`. Nu comite tu (User-ul face commit-urile).

## Teste

pytest cu fixtures HTML în `tests/fixtures/` — zero rețea.
