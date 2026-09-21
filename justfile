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

# sterge starea de scrape (run/) + datele generate; pastreaza localitati.json (versionat)
clean:
    rm -rf run/ site/data/parlamentari site/data/sigle site/data/meta.json

# dev server pentru frontend (Vite)
serve:
    cd site && npm run dev
