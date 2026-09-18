<script>
  let { p, sigle = {} } = $props()

  const RETELE = { facebook: 'Facebook', instagram: 'Instagram', x: 'X', linkedin: 'LinkedIn', youtube: 'YouTube', tiktok: 'TikTok' }

  let c = $derived(p.contacts ?? {})
  // socials e o lista de {retea: url}; scoate perechile [retea, url]
  let sociale = $derived(
    (c.socials ?? []).flatMap((s) => Object.entries(s)).filter(([k]) => k in RETELE)
  )

  // fara partid si fara organizatie de minoritate = independent de facto
  let independent = $derived(!p.partid && !p.organizatie)

  // siglele: cea curenta (partid / organizatie / independent) color, fostele
  // partide alb-negru, cronologic. Doar cele cu siglă reala; fara siglă -> nimic.
  let sigileList = $derived.by(() => {
    const out = []
    const vazute = new Set()
    const curent = p.partid_long ?? p.organizatie ?? (independent ? 'Indep.' : null)
    if (curent && sigle[curent]) {
      out.push({
        src: `data/${sigle[curent]}`, curent: true,
        nume: p.partid ?? p.organizatie ?? 'Independent',
      })
      vazute.add(curent)
    }
    // cel mai recent primul (dupa cel curent): descrescator dupa perioada
    const foste = Object.entries(p.partide_precedente ?? {})
      .sort((a, b) => b[0].localeCompare(a[0]))
      .map(([, nume]) => nume)
    for (const nume of foste) {
      if (vazute.has(nume) || !sigle[nume]) continue
      out.push({ src: `data/${sigle[nume]}`, curent: false, nume })
      vazute.add(nume)
    }
    return out
  })
</script>

<article class="card">
  {#if p.foto}
    <img src={p.foto} alt="" loading="lazy" />
  {:else}
    <div class="fara-foto">{p.prenume?.[0] ?? ''}{p.nume?.[0] ?? ''}</div>
  {/if}
  <div class="continut">
    <div class="antet">
      <h3>{p.prenume} {p.nume}</h3>
      {#if sigileList.length}
        <div class="sigle">
          {#each sigileList as s}
            <img class="sigla" class:fost={!s.curent} src={s.src} alt={s.nume}
                 title={s.curent ? s.nume : `${s.nume} (fost)`} loading="lazy" />
          {/each}
        </div>
      {/if}
    </div>

    <dl class="rubrici">
      <dt>Grup</dt>
      <dd>
        <span class="scurt">{p.grup}</span>
        {#if p.grup_long && p.grup_long !== p.grup}<span class="lung">{p.grup_long}</span>{/if}
        {#if p.afiliere === 'afiliat'}<span class="lung">(afiliat)</span>{/if}
      </dd>

      {#if p.organizatie}
        <dt>Organizație</dt>
        <dd>{p.organizatie}</dd>
      {:else}
        <dt>Partid</dt>
        <dd>
          {#if p.partid && p.partid !== 'Indep.'}
            <span class="scurt">{p.partid}</span>
            {#if p.partid_long && p.partid_long !== p.partid}<span class="lung">{p.partid_long}</span>{/if}
          {:else}
            <span class="scurt">independent</span>
          {/if}
          {#if p.partid_mandat && p.partid_mandat !== p.partid}
            <span class="mandat">mandat: {p.partid_mandat}</span>
          {/if}
        </dd>
      {/if}

      {#if c.official_email}
        <dt>Email oficial</dt>
        <dd><a href="mailto:{c.official_email}">{c.official_email}</a></dd>
      {/if}

      {#if c.other_emails?.length}
        <dt>Email</dt>
        <dd>
          {#each c.other_emails as email}
            <div><a href="mailto:{email}">{email}</a></div>
          {/each}
        </dd>
      {/if}

      {#if c.numbers?.length}
        <dt>Telefon</dt>
        <dd>
          {#each c.numbers as nr}
            <div><a href="tel:{nr.replace(/\s/g, '')}">{nr}</a></div>
          {/each}
        </dd>
      {/if}

      {#if c.offices?.length}
        <dt>Birou</dt>
        <dd>
          {#each c.offices as adresa}
            <div>{adresa}</div>
          {/each}
        </dd>
      {/if}

      <dt>Linkuri</dt>
      <dd class="linkuri">
        <a href={p.profil_url} target="_blank" rel="noopener">Profil oficial</a>
        {#if p.cv_url}
          · <a href={p.cv_url} target="_blank" rel="noopener">CV</a>
        {/if}
        {#if c.website}
          · <a href={c.website} target="_blank" rel="noopener">Site</a>
        {/if}
        {#each sociale as [retea, url]}
          · <a href={url} target="_blank" rel="noopener">{RETELE[retea]}</a>
        {/each}
      </dd>
    </dl>
  </div>
</article>

<style>
  .card {
    display: flex;
    gap: 1rem;
    background: var(--card);
    border: 1px solid var(--bordura);
    border-radius: 12px;
    box-shadow: var(--umbra);
    padding: 1rem;
  }

  img,
  .fara-foto {
    width: 150px;
    height: 200px; /* 3:4, portret */
    object-fit: cover;
    border-radius: 8px;
    flex-shrink: 0;
  }

  @media (max-width: 480px) {
    img,
    .fara-foto {
      width: 110px;
      height: 146px;
    }
  }

  .fara-foto {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bordura);
    color: var(--text-secundar);
    font-size: 1.3rem;
    font-weight: 600;
  }

  .continut {
    min-width: 0; /* permite wrap-ul textului lung in flex */
    flex: 1;
  }

  .antet {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    margin-bottom: 0.8rem;
  }

  .sigle {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex-shrink: 0;
  }

  .sigla {
    width: 50px;
    height: 50px;
    object-fit: contain;
  }

  /* fostele partide: alb-negru + estompate — nu mai sunt de actualitate
     (aceeasi marime; distinctia o dau grayscale + opacity) */
  .sigla.fost {
    filter: grayscale(1);
    opacity: 0.3;
  }

  h3 {
    font-size: 1.05rem;
  }

  /* grila de rubrici: eticheta | valoare */
  .rubrici {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.25rem 0.7rem;
    font-size: 0.9rem;
    margin: 0;
  }

  dt {
    color: var(--text-secundar);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    white-space: nowrap;
    padding-top: 0.05rem;
  }

  dd {
    margin: 0;
    word-break: break-word;
  }

  .scurt {
    font-weight: 600;
  }

  .lung {
    color: var(--text-secundar);
  }
  .lung::before {
    content: '· ';
  }

  .fara {
    color: var(--text-secundar);
    font-style: italic;
  }

  /* mandatul apare doar cand nu mai e in partidul cu care a fost ales (a trecut
     la altul SAU a plecat de tot) — informatie notabila, la fel in ambele cazuri */
  .mandat {
    color: #d9480f;
    font-weight: 700;
  }
  .mandat::before {
    content: '· ';
    color: var(--text-secundar);
    font-weight: 400;
  }

  @media (prefers-color-scheme: dark) {
    .mandat {
      color: #ff922b;
    }
  }

  @media (max-width: 480px) {
    /* pe mobil, eticheta deasupra valorii */
    .rubrici {
      grid-template-columns: 1fr;
      gap: 0.1rem;
    }
    dt {
      padding-top: 0.4rem;
    }
  }
</style>
