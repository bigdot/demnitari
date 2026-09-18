<script>
  let { localitati, onselect } = $props()

  const JUDETE = {
    AB: 'Alba', AR: 'Arad', AG: 'Argeș', BC: 'Bacău', BH: 'Bihor',
    BN: 'Bistrița-Năsăud', BT: 'Botoșani', BV: 'Brașov', BR: 'Brăila',
    BZ: 'Buzău', CS: 'Caraș-Severin', CL: 'Călărași', CJ: 'Cluj',
    CT: 'Constanța', CV: 'Covasna', DB: 'Dâmbovița', DJ: 'Dolj', GL: 'Galați',
    GR: 'Giurgiu', GJ: 'Gorj', HR: 'Harghita', HD: 'Hunedoara', IL: 'Ialomița',
    IS: 'Iași', IF: 'Ilfov', MM: 'Maramureș', MH: 'Mehedinți', MS: 'Mureș',
    NT: 'Neamț', OT: 'Olt', PH: 'Prahova', SM: 'Satu Mare', SJ: 'Sălaj',
    SB: 'Sibiu', SV: 'Suceava', TR: 'Teleorman', TM: 'Timiș', TL: 'Tulcea',
    VS: 'Vaslui', VL: 'Vâlcea', VN: 'Vrancea', B: 'București', DIA: 'Diaspora',
  }
  const judNume = (cod) => JUDETE[cod] ?? cod

  let query = $state('')
  let activ = $state(-1)
  let deschis = $state(false)

  function normalizeaza(s) {
    return s
      .normalize('NFKD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .trim()
  }

  // toate cuvintele din query trebuie sa fie prefixe de cuvinte din localitate:
  // "sector 5" -> "bucuresti sectorul 5", "cluj nap" -> "cluj-napoca".
  // Prioritate: potrivirile de la inceputul numelui, apoi restul.
  function sePotriveste(cauta, tokens) {
    const cuvinte = cauta.split(/[\s-]+/)
    return tokens.every((t) => cuvinte.some((c) => c.startsWith(t)))
  }

  // treapta de potrivire: exact (0) > prefix (1) > substring/token (2)
  function treapta(cauta, q) {
    if (cauta === q) return 0
    if (cauta.startsWith(q)) return 1
    return 2
  }

  let rezultate = $derived.by(() => {
    const q = normalizeaza(query)
    if (q.length < 2) return []
    const tokens = q.split(/[\s-]+/).filter(Boolean)
    const match = localitati.filter((l) => sePotriveste(l.cauta, tokens))
    match.sort((a, b) => {
      const ta = treapta(a.cauta, q)
      const tb = treapta(b.cauta, q)
      if (ta !== tb) return ta - tb
      // in aceeasi treapta: mai urban intai (rang mic = oras), apoi alfabetic
      if ((a.rang ?? 99) !== (b.rang ?? 99)) return (a.rang ?? 99) - (b.rang ?? 99)
      return a.nume.localeCompare(b.nume)
    })
    return match.slice(0, 12)
  })

  function alege(loc) {
    query = `${loc.nume} (${loc.judet})`
    deschis = false
    activ = -1
    onselect(loc)
  }

  function onkeydown(e) {
    if (!deschis || rezultate.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      activ = (activ + 1) % rezultate.length
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      activ = (activ - 1 + rezultate.length) % rezultate.length
    } else if (e.key === 'Enter' && activ >= 0) {
      e.preventDefault()
      alege(rezultate[activ])
    } else if (e.key === 'Escape') {
      deschis = false
    }
  }
</script>

<div class="cautare">
  <input
    type="text"
    placeholder="Scrie localitatea ta…"
    bind:value={query}
    oninput={() => { deschis = true; activ = -1 }}
    onkeydown={onkeydown}
    onfocus={() => (deschis = true)}
    aria-label="Caută localitatea"
    autocomplete="off"
  />
  {#if deschis && rezultate.length > 0}
    <ul class="sugestii">
      {#each rezultate as loc, i}
        <li>
          <button
            class:activ={i === activ}
            onmousedown={(e) => { e.preventDefault(); alege(loc) }}
          >
            <span class="loc-nume">{loc.nume}</span>
            <span class="judet">{judNume(loc.judet)} ({loc.judet})</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .cautare {
    position: relative;
    width: 100%;
  }

  input {
    width: 100%;
    font-size: 1.15rem;
    padding: 0.9rem 1.1rem;
    border: 1px solid var(--bordura);
    border-radius: 12px;
    background: var(--card);
    color: var(--text);
    box-shadow: var(--umbra);
    outline: none;
  }

  input:focus {
    border-color: var(--accent);
  }

  .sugestii {
    position: absolute;
    z-index: 10;
    width: 100%;
    margin-top: 0.4rem;
    list-style: none;
    background: var(--card);
    border: 1px solid var(--bordura);
    border-radius: 12px;
    box-shadow: var(--umbra);
    overflow: hidden;
  }

  .sugestii button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    width: 100%;
    padding: 0.6rem 1.1rem;
    border: none;
    background: none;
    color: var(--text);
    font-size: 1rem;
    text-align: left;
    cursor: pointer;
  }

  .loc-nume {
    font-weight: 500;
  }

  .sugestii button:hover,
  .sugestii button.activ {
    background: var(--accent);
    color: #fff;
  }

  /* judetul: badge clar, mereu vizibil */
  .judet {
    flex-shrink: 0;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    background: var(--bordura);
    color: var(--text-secundar);
    font-size: 0.8rem;
    font-weight: 600;
  }

  .sugestii button:hover .judet,
  .sugestii button.activ .judet {
    background: rgba(255, 255, 255, 0.25);
    color: #fff;
  }
</style>
