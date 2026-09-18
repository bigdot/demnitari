<script>
  import SearchBox from './SearchBox.svelte'
  import Card from './Card.svelte'

  let localitati = $state([])
  let selectata = $state(null)
  let date = $state(null)
  let eroare = $state(null)
  let seIncarca = $state(false)
  let meta = $state(null)
  let sigle = $state({}) // {nume partid -> cale logo}

  async function incarca() {
    const r = await fetch('data/localitati.json')
    localitati = await r.json()
    fetch('data/meta.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => (meta = m))
      .catch(() => {})
    fetch('data/sigle/manifest.json')
      .then((r) => (r.ok ? r.json() : {}))
      .then((s) => (sigle = s))
      .catch(() => {})
    // restaureaza selectia din hash (#<siruta>) — linkurile se pot da mai departe
    const siruta = parseInt(location.hash.slice(1), 10)
    if (siruta >= 0) {
      const loc = localitati.find((l) => l.siruta === siruta)
      if (loc) alege(loc)
    }
  }

  async function alege(loc) {
    selectata = loc
    location.hash = String(loc.siruta)
    eroare = null
    date = null
    seIncarca = true
    try {
      const r = await fetch(`data/parlamentari/${loc.judet}.json`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      date = await r.json()
    } catch (e) {
      eroare = 'Nu am putut încărca datele. Încearcă din nou.'
    } finally {
      seIncarca = false
    }
  }

  incarca()
</script>

<main>
  <header>
    <h1>Cine te reprezintă?</h1>
  </header>

  <SearchBox {localitati} onselect={alege} />

  {#if seIncarca}
    <p class="stare">Se încarcă…</p>
  {:else if eroare}
    <p class="stare">{eroare}</p>
  {:else if date}
    <p class="circ">
      Circumscripția nr. {date.circumscriptie.nr} — {date.circumscriptie.nume}
    </p>

    <section>
      <h2>Deputați</h2>
      <div class="lista">
        {#each date.deputati as p}
          <Card {p} {sigle} />
        {/each}
      </div>
    </section>

    <section>
      <h2>Senatori</h2>
      <div class="lista">
        {#each date.senatori as p}
          <Card {p} {sigle} />
        {/each}
      </div>
    </section>
  {/if}

  <footer>
    {#if date}
      <span>Actualizat: {date.actualizat}</span>
    {:else if meta}
      <span>Actualizat: {meta.actualizat?.slice(0, 10)}</span>
    {/if}
  </footer>
</main>

<style>
  main {
    max-width: 720px;
    margin: 0 auto;
    padding: 1.2rem 1rem 3rem;
  }

  header {
    text-align: center;
    padding: 2.2rem 0 1.4rem;
  }

  h1 {
    font-size: 1.7rem;
  }

  .stare {
    text-align: center;
    color: var(--text-secundar);
    padding: 2rem 0;
  }

  .circ {
    color: var(--text-secundar);
    font-size: 0.9rem;
    padding: 1.2rem 0 0.4rem;
  }

  section {
    margin-top: 1rem;
  }

  h2 {
    font-size: 1.15rem;
    margin-bottom: 0.6rem;
  }

  .lista {
    display: grid;
    gap: 0.7rem;
  }

  footer {
    margin-top: 2.5rem;
    text-align: center;
    color: var(--text-secundar);
    font-size: 0.8rem;
  }
</style>
