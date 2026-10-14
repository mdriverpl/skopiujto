<script setup>
import { computed, onMounted, ref } from 'vue'
import { Mail, ExternalLink, Plus, Search, RefreshCw, Pencil, Trash2, Save, X, Settings } from 'lucide-vue-next'
import EDeliverySettings from './EDeliverySettings.vue'
const props = defineProps({ api: Function })
const records = ref([]), search = ref(''), direction = ref('all'), status = ref('all')
const draft = ref(null), busy = ref(false), loaded = ref(false), error = ref('')
const connection = ref(null), settingsOpen = ref(false), notice = ref('')
const statuses = { registered: 'Zarejestrowana', sent: 'Wysłana', delivered: 'Doręczona', received: 'Odebrana', failed: 'Nieudana' }
const directions = { incoming: 'Przychodząca', outgoing: 'Wychodząca' }
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium' }).format(new Date(`${value}T12:00:00`))
const filtered = computed(() => records.value.filter(item =>
  (direction.value === 'all' || item.direction === direction.value) && (status.value === 'all' || item.status === status.value) &&
  `${item.title} ${item.correspondent} ${item.address} ${item.reference} ${item.notes}`.toLocaleLowerCase('pl').includes(search.value.trim().toLocaleLowerCase('pl'))))
async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action() } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function load() { records.value = await props.api('/edeliveries'); loaded.value = true; connection.value = await props.api('/edeliveries/connection') }
function settingsSaved(value) { connection.value = value }
async function sync() { await run(async () => { const result = await props.api('/edeliveries/sync', 'POST'); notice.value = result.message; if (result.more) notice.value += ' Skrzynka zawiera także starsze przesyłki poza zakresem synchronizacji.'; await load() }) }
function edit(item) {
  if (busy.value) return
  if (item?.message_id) { error.value = 'Dane tej przesyłki pochodzą ze skrzynki i aktualizuje je synchronizacja.'; return }
  error.value = ''
  draft.value = item ? { ...item } : { title: '', correspondent: '', address: '', reference: '', direction: 'incoming', status: 'registered', record_date: today(), notes: '' }
}
async function save() {
  if (!draft.value?.title.trim() || !draft.value.correspondent.trim() || !draft.value.record_date) return
  await run(async () => {
    const item = draft.value
    const body = { title: item.title.trim(), correspondent: item.correspondent.trim(), address: item.address, reference: item.reference, direction: item.direction, status: item.status, record_date: item.record_date, notes: item.notes, ...(item.id ? { version: item.version } : {}) }
    const saved = await props.api(item.id ? `/edeliveries/${item.id}` : '/edeliveries', item.id ? 'PATCH' : 'POST', body)
    records.value = [saved, ...records.value.filter(record => record.id !== saved.id)].sort((a, b) => b.record_date.localeCompare(a.record_date) || b.created_at.localeCompare(a.created_at))
    draft.value = null
  })
}
async function remove(item) {
  if (busy.value || !window.confirm(`Usunąć przesyłkę „${item.title}” z rejestru?`)) return
  await run(async () => { await props.api(`/edeliveries/${item.id}`, 'DELETE'); records.value = records.value.filter(record => record.id !== item.id) })
}
onMounted(() => run(load))
</script>

<template>
  <section class="edelivery-page" aria-label="eDoręczenia">
    <Teleport to="#workspace-title"><div><h1>eDoręczenia <small>({{ records.length }})</small></h1><p>Twój rejestr korespondencji elektronicznej.</p></div></Teleport>
    <Teleport to="#workspace-search"><div class="search"><Search :size="18" /><input v-model="search" aria-label="Szukaj przesyłki" placeholder="Temat, nadawca, odbiorca, numer…" /></div></Teleport>
    <nav class="page-menu" aria-label="Menu eDoręczeń">
      <button class="primary" :disabled="busy" @click="edit()"><Plus :size="17" /> Dodaj przesyłkę</button>
      <button :disabled="busy" aria-label="Odśwież rejestr przesyłek" @click="run(load)"><RefreshCw :size="17" /> Odśwież</button>
      <button :disabled="busy" @click="settingsOpen = true"><Settings :size="17" /> Konfiguracja skrzynki</button>
      <button :disabled="busy || !connection?.enabled" @click="sync"><RefreshCw :size="17" /> Synchronizuj skrzynkę</button>
      <select v-model="direction" aria-label="Kierunek przesyłki"><option value="all">Oba kierunki</option><option v-for="(label, key) in directions" :key="key" :value="key">{{ label }}</option></select>
      <select v-model="status" aria-label="Status przesyłki"><option value="all">Wszystkie statusy</option><option v-for="(label, key) in statuses" :key="key" :value="key">{{ label }}</option></select>
      <a class="edelivery-link" href="https://edoreczenia.gov.pl/" target="_blank" rel="noopener noreferrer"><Mail :size="17" /> Otwórz skrzynkę <ExternalLink :size="15" /><span class="sr-only"> (nowa karta)</span></a>
    </nav>
    <p class="register-note">{{ connection?.enabled ? `Połączenie skonfigurowane: ${connection.address}. Synchronizacja pobiera metadane do 500 najnowszych przesyłek, bez otwierania ich treści.` : 'Podłącz skrzynkę w Konfiguracji skrzynki lub dodawaj przesyłki ręcznie.' }} Rejestr jest widoczny tylko dla Ciebie. Dodanie wpisu nie wysyła korespondencji.</p>
    <p v-if="notice" class="success" role="status">{{ notice }}</p>
    <EDeliverySettings v-if="settingsOpen" :api="api" :initial="connection" @saved="settingsSaved" @close="settingsOpen = false" />
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="busy && !loaded" role="status">Wczytywanie rejestru…</p>
    <div v-if="loaded" class="panel register-table"><table><thead><tr><th>Data przesyłki</th><th>Temat / numer</th><th>Nadawca / odbiorca</th><th>Kierunek</th><th>Status</th><th>Akcje</th></tr></thead><tbody><tr v-for="item in filtered" :key="item.id"><td>{{ date(item.record_date) }}</td><td><button class="record-title" :disabled="busy || !!item.message_id" @click="edit(item)">{{ item.title }}</button><small v-if="item.reference">{{ item.reference }}</small><small v-if="item.message_id">UA API</small></td><td>{{ item.correspondent }}<small v-if="item.address">{{ item.address }}</small></td><td>{{ directions[item.direction] }}</td><td><span class="delivery-status" :class="item.status">{{ item.remote_status || statuses[item.status] }}</span></td><td class="record-actions"><button class="icon-button" :disabled="busy || !!item.message_id" :aria-label="`Edytuj przesyłkę: ${item.title}`" @click="edit(item)"><Pencil :size="17" /></button><button class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń przesyłkę: ${item.title}`" @click="remove(item)"><Trash2 :size="17" /></button></td></tr></tbody></table><p v-if="!filtered.length" class="empty">{{ records.length ? 'Brak przesyłek pasujących do filtrów.' : 'Rejestr jest pusty. Dodaj pierwszą przesyłkę.' }}</p></div>
    <div v-if="draft" class="modal-backdrop" @keydown.esc="!busy && (draft = null)"><section class="panel delivery-dialog" role="dialog" aria-modal="true" aria-labelledby="delivery-title"><header class="editor-heading"><h2 id="delivery-title">{{ draft.id ? 'Edytuj przesyłkę' : 'Dodaj przesyłkę' }}</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij formularz przesyłki" @click="draft = null"><X :size="20" /></button></header><form @submit.prevent="save"><p v-if="error" class="error" role="alert">{{ error }}</p><label>Temat<input v-model="draft.title" required maxlength="200" autofocus :disabled="busy" /></label><div class="form-grid"><label>Kierunek<select v-model="draft.direction" :disabled="busy"><option v-for="(label, key) in directions" :key="key" :value="key">{{ label }}</option></select></label><label>Status<select v-model="draft.status" :disabled="busy"><option v-for="(label, key) in statuses" :key="key" :value="key">{{ label }}</option></select></label></div><label>{{ draft.direction === 'incoming' ? 'Nadawca' : 'Odbiorca' }}<input v-model="draft.correspondent" required maxlength="200" :disabled="busy" /></label><label>Adres do eDoręczeń (opcjonalnie)<input v-model="draft.address" maxlength="200" placeholder="AE:…" :disabled="busy" /></label><div class="form-grid"><label>Numer przesyłki (opcjonalnie)<input v-model="draft.reference" maxlength="200" :disabled="busy" /></label><label>Data przesyłki<input v-model="draft.record_date" type="date" required :disabled="busy" /></label></div><label>Notatki<textarea v-model="draft.notes" rows="4" maxlength="20000" :disabled="busy" /></label><footer class="editor-actions"><button type="button" :disabled="busy" @click="draft = null">Anuluj</button><button class="primary" :disabled="busy || !draft.title.trim() || !draft.correspondent.trim()"><Save :size="17" /> {{ busy ? 'Zapisywanie…' : 'Zapisz przesyłkę' }}</button></footer></form></section></div>
  </section>
</template>

<style scoped>
.edelivery-link { display:inline-flex; flex:0 0 auto; align-items:center; gap:8px; min-height:38px; padding:9px 13px; border:1px solid var(--border); border-radius:9px; background:var(--surface); color:var(--text); text-decoration:none; white-space:nowrap; font-size:12px; }
.edelivery-link:hover { background:var(--accent-soft); }
.register-note { font-size:12px; color:var(--muted); line-height:1.7; margin:0 0 20px; }
.register-table { overflow-x:auto; } table { width:100%; border-collapse:collapse; font-size:13px; } th,td { text-align:left; padding:16px; border-bottom:1px solid var(--border); } th { background:var(--surface-soft); color:var(--muted); font-size:12px; white-space:nowrap; } td { max-width:320px; overflow-wrap:anywhere; } td small { display:block; color:var(--muted); margin-top:6px; }
.record-title { border:0; background:transparent; padding:0; text-align:left; font-weight:600; } .record-actions { white-space:nowrap; } .delivery-status { display:inline-block; padding:5px 9px; border-radius:7px; background:var(--accent-soft); color:var(--accent); white-space:nowrap; font-size:12px; } .delivery-status.delivered,.delivery-status.received { background:var(--success-soft); color:var(--success); } .delivery-status.failed { background:var(--danger-soft); color:var(--danger); }
.delivery-dialog { width:min(650px,100%); max-height:90dvh; overflow-y:auto; padding:24px; } .editor-heading h2 { margin:0; } .delete-button { color:var(--danger); } .sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
@media(max-width:600px) { .delivery-dialog { padding:18px; } .form-grid { grid-template-columns:1fr; } }
</style>
