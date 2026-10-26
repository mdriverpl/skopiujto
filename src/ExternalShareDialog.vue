<script setup>
import { computed, onMounted, ref } from 'vue'
import { X, Link, Copy, Folder, Images, LayoutGrid, Eye, ShieldCheck } from 'lucide-vue-next'
const props = defineProps({ api: Function, resource: Object })
const emit = defineEmits(['close'])
const view = ref(props.resource.kind === 'folder' ? 'catalog' : 'preview'), hours = ref(168)
const allowUploads = ref(false)
const links = ref([]), created = ref(null), busy = ref(false), loading = ref(true), error = ref(''), copied = ref(false)
const modes = computed(() => [
  { id: 'catalog', label: 'Katalog', icon: Folder, description: 'Czytelna lista plików i podkatalogów.' },
  { id: 'gallery', label: 'Galeria', icon: Images, description: 'Duże miniatury zdjęć i obrazów.' },
  { id: 'tiles', label: 'Kafelki', icon: LayoutGrid, description: 'Karty plików z nazwami i ikonami.' },
  ...(props.resource.kind === 'document' ? [{ id: 'preview', label: 'Podgląd', icon: Eye, description: 'Otwórz od razu podgląd pliku lub dokumentu.' }] : [])
])
const endpoint = computed(() => `/external-links/${props.resource.kind}/${encodeURIComponent(props.resource.id)}`)
const address = computed(() => created.value ? new URL(created.value.path, location.origin).href : '')
const active = link => !link.revoked && link.expires * 1000 > Date.now()
const date = stamp => new Date(stamp * 1000).toLocaleString('pl-PL')
async function load() { links.value = await props.api(endpoint.value) }
async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action() } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function create() {
  await run(async () => {
    created.value = await props.api(endpoint.value, 'POST', { view_mode: view.value, hours: hours.value, allow_uploads: allowUploads.value })
    copied.value = false; await load()
  })
}
async function change(link, mode) {
  await run(async () => { await props.api(`/external-links/${link.id}`, 'PATCH', { view_mode: mode }); await load() })
}
async function changeUploads(link, event) {
  await run(async () => { await props.api(`/external-links/${link.id}`, 'PATCH', { allow_uploads: event.target.checked }); await load() })
  event.target.checked = !!links.value.find(item => item.id === link.id)?.allow_uploads
}
async function revoke(link) {
  await run(async () => {
    await props.api(`/external-links/${link.id}`, 'DELETE')
    if (created.value?.id === link.id) created.value = null
    await load()
  })
}
async function copy() {
  try { await navigator.clipboard.writeText(address.value); copied.value = true }
  catch { error.value = 'Skopiuj link z pola poniżej.' }
}
onMounted(async () => { try { await load() } catch (err) { error.value = err.message } finally { loading.value = false } })
</script>
<template>
  <div class="external-share-backdrop" @click.self="!busy && emit('close')" @keydown.esc.stop="!busy && emit('close')">
    <section class="external-share-dialog" role="dialog" aria-modal="true" aria-labelledby="external-share-title">
      <header><div><span class="share-eyebrow"><Link :size="15" />Link zewnętrzny</span><h2 id="external-share-title">Udostępnij {{ resource.kind === 'folder' ? 'katalog' : 'plik' }}</h2><p>{{ resource.name || resource.title }}</p></div><button class="share-close" :disabled="busy" aria-label="Zamknij udostępnianie" @click="emit('close')"><X :size="20" /></button></header>
      <p v-if="error" class="share-error" role="alert">{{ error }}</p>
      <form @submit.prevent="create">
        <fieldset :disabled="busy || loading"><legend>Sposób prezentacji</legend><div class="share-modes"><label v-for="mode in modes" :key="mode.id" :class="{ chosen: view === mode.id }"><input v-model="view" type="radio" name="share-mode" :value="mode.id" /><component :is="mode.icon" :size="22" /><strong>{{ mode.label }}</strong><small>{{ mode.description }}</small></label></div>
        <label class="share-expiration">Ważność linku<select v-model.number="hours"><option :value="24">24 godziny</option><option :value="168">7 dni</option><option :value="720">30 dni</option><option :value="2160">90 dni</option></select></label>
        <label v-if="resource.kind === 'folder'" class="share-upload-permission"><input v-model="allowUploads" type="checkbox" />Zezwalaj odbiorcom linku na dodawanie zdjęć</label></fieldset>
        <p class="share-note"><ShieldCheck :size="17" /><span>Osoba z linkiem otworzy zasób bez logowania. {{ resource.kind === 'folder' ? 'Katalog obejmuje Twoje pliki i podkatalogi; zmiany zawartości są widoczne pod tym samym linkiem.' : 'Link pokazuje aktualną wersję pliku.' }} Możesz wyłączyć dostęp w każdej chwili.</span></p>
        <button type="submit" class="primary" :disabled="busy || loading"><Link :size="16" />{{ busy ? 'Zapisywanie…' : 'Utwórz link' }}</button>
      </form>
      <section v-if="created" class="share-created" aria-label="Gotowy link"><strong>Link jest gotowy</strong><label>Adres do udostępnienia<input :value="address" readonly aria-label="Link zewnętrzny" @focus="$event.target.select()" /></label><div><button :disabled="busy" @click="copy"><Copy :size="15" />{{ copied ? 'Skopiowano' : 'Kopiuj link' }}</button><a :href="address" target="_blank" rel="noopener noreferrer">Otwórz podgląd</a></div><small>Ważny do {{ date(created.expires) }}. Skopiuj adres przed zamknięciem okna.</small></section>
      <section class="share-history"><h3>Utworzone linki</h3><p v-if="loading" role="status">Wczytywanie…</p><p v-else-if="!links.length">Brak linków do tego zasobu.</p><article v-for="link in links" :key="link.id"><div><strong>{{ active(link) ? 'Aktywny link' : link.revoked ? 'Wyłączony link' : 'Link wygasł' }}</strong><small>Ważny do {{ date(link.expires) }}</small></div><label v-if="resource.kind === 'folder'" class="share-upload-permission"><input type="checkbox" :checked="!!link.allow_uploads" :disabled="busy || !active(link)" :aria-label="'Dodawanie zdjęć przez odbiorców linku'" @change="changeUploads(link, $event)" />Dodawanie zdjęć</label><label><span class="share-sr-only">Widok linku</span><select :value="link.view_mode" :disabled="busy || !active(link)" aria-label="Widok linku" @change="change(link, $event.target.value)"><option v-for="mode in modes" :key="mode.id" :value="mode.id">{{ mode.label }}</option></select></label><button v-if="active(link)" class="share-revoke" :disabled="busy" @click="revoke(link)">Wyłącz</button></article></section>
    </section>
  </div>
</template>
<style scoped>
.external-share-backdrop { position:fixed; inset:0; z-index:110; display:grid; place-items:center; padding:20px; background:#15213d66; backdrop-filter:blur(5px); }.external-share-dialog { width:min(660px,100%); max-height:92dvh; overflow-y:auto; box-sizing:border-box; border:1px solid var(--border); border-radius:20px; background:var(--surface); padding:26px; color:var(--text); }.external-share-dialog header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }.share-eyebrow { display:flex; align-items:center; gap:7px; color:var(--accent); font-size:11px; }.external-share-dialog h2 { font-size:21px; margin:10px 0 7px; }.external-share-dialog header p { color:var(--muted); margin:0 0 22px; overflow-wrap:anywhere; font-size:12px; }.share-close { padding:5px; border:0; background:transparent; }fieldset { padding:0; margin:0; border:0; min-width:0; }legend { font-size:12px; font-weight:600; margin-bottom:12px; }.share-modes { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:9px; }.share-modes label { display:flex; flex-direction:column; gap:9px; position:relative; padding:15px 12px; border:1px solid var(--border); border-radius:12px; cursor:pointer; }.share-modes input { position:absolute; top:12px; right:10px; width:13px; height:13px; margin:0; }.share-modes .chosen { border-color:var(--accent); background:var(--accent-soft); }.share-modes svg { color:var(--accent); }.share-modes strong { font-size:12px; }.share-modes small { color:var(--muted); font-size:10px; line-height:1.6; }.share-expiration { display:grid; grid-template-columns:1fr 1fr; align-items:center; gap:12px; margin-top:18px; font-size:12px; }select,input:not([type=radio]):not([type=checkbox]) { width:100%; min-width:0; box-sizing:border-box; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--text); font:inherit; font-size:12px; }.share-note { display:flex; align-items:flex-start; gap:9px; padding:13px; margin:18px 0; border-radius:10px; background:var(--surface-soft); color:var(--muted); font-size:11px; line-height:1.8; }.share-note svg { flex-shrink:0; margin-top:2px; color:var(--accent); }button,a { display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:9px 12px; border:1px solid var(--border); border-radius:8px; color:var(--secondary); background:var(--surface); font-size:12px; text-decoration:none; }button.primary { background:var(--accent); color:white; border-color:var(--accent); }.share-created { display:grid; gap:12px; padding:16px; margin-top:20px; background:var(--accent-soft); border-radius:12px; }.share-created>label { display:grid; gap:8px; font-size:11px; }.share-created>div { display:flex; gap:8px; flex-wrap:wrap; }.share-created small { color:var(--muted); font-size:10px; line-height:1.6; }.share-history { border-top:1px solid var(--border); margin-top:22px; padding-top:16px; }.share-history h3 { font-size:13px; margin:0 0 12px; }.share-history>p { font-size:11px; color:var(--muted); }.share-history article { display:flex; align-items:center; gap:9px; padding:12px 0; border-bottom:1px solid var(--border); }.share-history article>div { flex:1; }.share-history strong { font-size:11px; }.share-history small { display:block; margin-top:5px; color:var(--muted); font-size:10px; }.share-history select { max-width:100px; }.share-revoke,.share-error { color:var(--theme-danger,#ba253b); }.share-error { font-size:12px; }.share-sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); }button:disabled { opacity:.55; }
@media(max-width:550px) { .external-share-dialog { padding:19px; }.share-modes { grid-template-columns:repeat(2,minmax(0,1fr)); }.share-history article { flex-wrap:wrap; }.share-history article>div { min-width:100%; } }
.share-upload-permission { display:flex; align-items:center; gap:8px; font-size:11px; line-height:1.5; margin-top:14px; }.share-upload-permission input { width:14px; height:14px; flex-shrink:0; accent-color:var(--accent); }.share-history article { flex-wrap:wrap; }.share-history .share-upload-permission { margin-top:0; max-width:140px; }
</style>
