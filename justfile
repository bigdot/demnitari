# demnitari — daily data build + frontend

# scrie site/data/parlamentari/*.json + meta.json (~17 min, ~1000 requesturi la 1/sec)
# `just scrape` = daily; `just scrape --continue` = reia partialul zilei;
# `just scrape --all` = forteaza tot (ignora cache-ul). Receipt-ul sta in run/.
scrape *args:
    uv run python -m scrapers {{args}}

# construieste site/data/localitati.json din nomenclatorul SIRUTA
fetch-addresses:
    uv run python -m scrapers.localitati

# ruleaza testele (pytest, offline cu fixtures)
test *args:
    uv run pytest {{args}}

# dev server pentru frontend (Vite)
serve:
    cd site && npm run dev

# urca schimbarile: intai datele din submodul (daca exista), apoi codul +
# bump-ul de pointer. Push pe master -> GitHub Actions publica pe Pages.
# Ex: `just deploy "fix autocomplete"` (mesaj optional).
# (scrape-ul de date NU se declanseaza de aici - pe ala il ruleaza cronul zilnic)
deploy mesaj="update":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "$(git -C site/data status --porcelain)" ]; then
        git -C site/data add -A
        git -C site/data commit -m "data: {{mesaj}} ($(date +%F))"
        git -C site/data push origin HEAD:master
    fi
    git add -A
    git commit -m "{{mesaj}}" || echo "(nimic de comis in codul aplicatiei)"
    git push origin master
