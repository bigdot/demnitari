import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  // relative base: site-ul e servit pe GitHub Pages sub /demnitari/
  base: './',
  plugins: [svelte()],
  // datele (submodulul site/data) sunt servite direct de dev server din root;
  // la build le copiaza scriptul din package.json in dist/data
  publicDir: false,
})
