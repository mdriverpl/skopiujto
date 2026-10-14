<script setup>
import { computed, onMounted, ref } from 'vue'
import { Sparkles, Plus, Search, Pencil, Trash2, X, Save, RefreshCw, Database } from 'lucide-vue-next'
import { fieldKey } from './documentFields.js'

const props = defineProps({ api: Function })
const profiles = ref([]), search = ref(''), busy = ref(false), loaded = ref(false)
const error = ref(''), formError = ref(''), notice = ref(''), draft = ref(null), deleting = ref(null)
const suggestions = ['miejsce zawarcia umowy', 'nazwa sprzedającego', 'adres sprzedającego', 'NIP sprzedającego',
  'nazwa zamawiającego', 'adres zamawiającego', 'NIP zamawiającego', 'imię kupującego', 'adres kupującego']
let rowId = 0
let initialDraft = ''
const filtered = computed(() => {
  const query = search.value.trim().toLocaleLowerCase('pl')
  return profiles.value.filter(item => `${item.name} ${Object.entries(item.fields).flat().join(' ')}`.toLocaleLowerCase('pl').includes(query))
    .sort((a, b) => a.name.localeCompare(b.name, 'pl'))
})
const tableRows = computed(() => filtered.value.flatMap(item => Object.entries(item.fields).map(([label, value]) => ({ item, label, value }))))
const fieldCount = computed(() => profiles.value.reduce((count, item) => count + Object.keys(item.fields).length, 0))
const snapshot = () => JSON.stringify(draft.value)
async function load() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { profiles.value = await props.api('/saved-data'); loaded.value = true }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
function open(item = null) {
  if (busy.value) return
  draft.value = { id: item?.id || null, version: item?.version, name: item?.name || '',
    rows: item ? Object.entries(item.fields).map(([label, value]) => ({ id: ++rowId, label, value }))
      : [{ id: ++rowId, label: '', value: '' }] }
  initialDraft = snapshot(); formError.value = ''; notice.value = ''
}
function close() {
  if (busy.value) return
  if (snapshot() !== initialDraft && !window.confirm('Zamknąć bez zapisywania zmian?')) return
  draft.value = null; formError.value = ''
}
function addRow() {
  if (!busy.value && draft.value && draft.value.rows.length < 200) draft.value.rows.push({ id: ++rowId, label: '', value: '' })
}
function removeRow(id) {
  if (!busy.value && draft.value?.rows.length > 1) draft.value.rows = draft.value.rows.filter(row => row.id !== id)
}
async function save() {
  if (busy.value || !draft.value) return
  formError.value = ''
  const fields = {}, keys = new Set()
  for (const row of draft.value.rows) {
    const label = row.label.trim(), key = fieldKey(label)
    if (!label && !row.value.trim()) continue
    if (!label || !row.value.trim()) { formError.value = 'Każde pole musi mieć nazwę i wartość.'; return }
    if (/[\[\]\r\n]/.test(label)) { formError.value = 'Wpisz nazwę pola bez nawiasów i nowych linii.'; return }
    if (keys.has(key)) { formError.value = `Nazwa pola „${label}” powtarza się.`; return }
    keys.add(key); Object.defineProperty(fields, key, { value: row.value, enumerable: true, configurable: true })
  }
  if (!keys.size) { formError.value = 'Dodaj co najmniej jedno pole z wartością.'; return }
  busy.value = true
  try {
    const updating = !!draft.value.id
    const saved = await props.api(updating ? `/saved-data/${draft.value.id}` : '/saved-data', updating ? 'PUT' : 'POST', {
      name: draft.value.name || Object.keys(fields)[0].slice(0, 100), fields, ...(updating ? { version: draft.value.version } : {}),
    })
    profiles.value = [...profiles.value.filter(item => item.id !== saved.id), saved]
    draft.value = null; notice.value = updating ? 'Dane zaktualizowane.' : 'Dane zapisane.'
  } catch (err) { formError.value = err.message }
  finally { busy.value = false }
}
async function remove() {
  if (busy.value || !deleting.value) return
  busy.value = true; formError.value = ''
  try {
    const id = deleting.value.id
    await props.api(`/saved-data/${id}`, 'DELETE')
    profiles.value = profiles.value.filter(item => item.id !== id)
    deleting.value = null; notice.value = 'Zestaw usunięty. Dane dokumentów pozostały bez zmian.'
  } catch (err) { formError.value = err.message }
  finally { busy.value = false }
}
function confirmRemoval(item) { if (!busy.value) { deleting.value = item; formError.value = '' } }
onMounted(load)
</script>

<template>
  <section class="ai-data-panel" aria-labelledby="ai-title">
    <header class="ai-heading"><Teleport to="#workspace-title"><div class="ai-heading-copy"><span class="ai-mark"><Sparkles :size="24" /></span><div><h1 id="ai-title">AI</h1><p>Twoje dane, gotowe do kolejnych dokumentów.</p></div></div></Teleport><div class="ai-heading-actions"><slot name="actions" /><button class="primary" :disabled="busy" @click="open()"><Plus :size="17" /> Dodaj dane</button></div></header>
    <div class="ai-data-intro"><Database :size="18" /><p><strong>{{ profiles.length }} zestawów · {{ fieldCount }} zapisanych pól</strong><span>Dane są prywatne i zapamiętywane podczas wpisywania. AI automatycznie dopasowuje je w kolejnych dokumentach.</span></p></div>
    <div class="ai-data-toolbar"><Teleport to="#workspace-search"><div class="search"><Search :size="17" /><input v-model="search" aria-label="Szukaj zapisanych danych" placeholder="Szukaj zestawu, pola lub wartości…" /></div></Teleport><button :disabled="busy" @click="load"><RefreshCw :size="16" /> Odśwież</button></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="ai-notice" role="status">{{ notice }}</p>
    <p v-if="!loaded && busy" class="ai-empty" role="status">Wczytywanie zapisanych danych…</p>
    <div v-else-if="loaded && !filtered.length" class="ai-empty"><Database :size="30" /><h2>{{ search.trim() ? 'Brak pasujących danych' : 'Zapisz dane raz, używaj wielokrotnie' }}</h2><p>{{ search.trim() ? 'Zmień wyszukiwaną nazwę lub wartość.' : 'Dodaj miejsce zawarcia umowy, dane swojej firmy lub kontrahenta.' }}</p><button v-if="!search.trim()" :disabled="busy" @click="open()"><Plus :size="16" /> Dodaj pierwszy zestaw</button></div>
    <div v-if="tableRows.length" class="ai-data-table panel"><table><thead><tr><th>Pole</th><th>Wartość</th><th>Akcje</th></tr></thead><tbody><tr v-for="row in tableRows" :key="`${row.item.id}:${row.label}`"><td>{{ row.label }}</td><td>{{ row.value }}</td><td class="ai-table-actions"><button class="icon-button" :disabled="busy" aria-label="Edytuj zapisane dane" @click="open(row.item)"><Pencil :size="16" /></button><button class="icon-button" :disabled="busy" aria-label="Usuń zapisane dane" @click="confirmRemoval(row.item)"><Trash2 :size="16" /></button></td></tr></tbody></table></div>
  </section>
  <div v-if="draft" class="modal-backdrop"><section class="panel ai-data-editor" role="dialog" aria-modal="true" aria-labelledby="data-editor-title"><header class="editor-heading"><div><h2 id="data-editor-title">{{ draft.id ? 'Edytuj zapisane dane' : 'Dodaj dane' }}</h2><p>Nazwy pól powinny odpowiadać polom w szablonie.</p></div><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="close"><X :size="20" /></button></header>
    <form @submit.prevent="save"><div class="ai-form-scroll"><p v-if="formError" class="error" role="alert">{{ formError }}</p><p class="ai-field-help">Wpisz nazwę bez nawiasów, np. „adres zamawiającego” dla pola [adres zamawiającego].</p><datalist id="saved-field-names"><option v-for="label in suggestions" :key="label" :value="label" /></datalist><div v-for="(row, index) in draft.rows" :key="row.id" class="ai-field-row"><label>Nazwa pola<input v-model="row.label" list="saved-field-names" maxlength="120" :disabled="busy" placeholder="np. miejsce zawarcia umowy" /></label><label>Wartość<textarea v-model="row.value" rows="2" maxlength="2000" :disabled="busy" placeholder="Wpisz dane…" /></label><button type="button" class="icon-button" :disabled="busy || draft.rows.length === 1" :aria-label="`Usuń pole ${index + 1}`" @click="removeRow(row.id)"><Trash2 :size="16" /></button></div><button type="button" :disabled="busy || draft.rows.length >= 200" @click="addRow"><Plus :size="16" /> Dodaj pole</button></div><footer class="editor-actions"><button type="button" :disabled="busy" @click="close">Anuluj</button><button type="submit" class="primary" :disabled="busy"><Save :size="16" /> {{ busy ? 'Zapisywanie…' : 'Zapisz dane' }}</button></footer></form>
  </section></div>
  <div v-if="deleting" class="modal-backdrop"><section class="panel ai-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="data-delete-title"><h2 id="data-delete-title">Usunąć zestaw „{{ deleting.name }}”?</h2><p>Uzupełnione dokumenty zachowają swoje dane.</p><p v-if="formError" class="error" role="alert">{{ formError }}</p><div class="editor-actions"><button :disabled="busy" @click="deleting = null">Anuluj</button><button :disabled="busy" class="ai-delete-button" @click="remove"><Trash2 :size="16" /> Usuń zestaw</button></div></section></div>
</template>

<style scoped>
.ai-heading-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.ai-data-table { overflow-x: auto; }.ai-data-table table { width: 100%; border-collapse: collapse; font-size: 13px; }.ai-data-table th, .ai-data-table td { text-align: left; padding: 15px 18px; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; white-space: pre-wrap; }.ai-data-table th { background: var(--surface-soft); color: var(--muted); font-size: 11px; }.ai-data-table td:nth-child(2) { min-width: 220px; }.ai-table-actions { width: 100px; white-space: nowrap !important; }.ai-table-actions button { display: inline-flex; }

.ai-heading, .ai-heading-copy, .ai-data-toolbar, .ai-data-card header, .ai-card-actions { display: flex; align-items: center; gap: 12px; }
.ai-heading { justify-content: space-between; margin: 24px 0; flex-wrap: wrap; }
.ai-heading h1 { margin: 0; font-size: 26px; }.ai-heading p { margin: 6px 0 0; color: var(--muted); font-size: 13px; }
.ai-mark, .ai-card-icon { display: grid; place-items: center; background: var(--accent-soft); color: var(--theme-accent, #7764dc); border-radius: 14px; flex-shrink: 0; }.ai-mark { width: 54px; height: 54px; }.ai-card-icon { width: 40px; height: 40px; }
.ai-data-intro { display: flex; align-items: center; gap: 12px; padding: 16px 20px; border: 1px solid var(--theme-accent-soft, #e7e1fa); background: var(--theme-accent-soft, #f4f1fd); border-radius: 14px; color: var(--accent); }.ai-data-intro p { margin: 0; }.ai-data-intro strong, .ai-data-intro span { display: block; font-size: 12px; }.ai-data-intro span { color: var(--muted); margin-top: 5px; line-height: 1.6; }
.ai-data-toolbar { justify-content: space-between; margin: 22px 0; flex-wrap: wrap; }.ai-data-toolbar .search { flex: 1; max-width: 550px; }.ai-data-toolbar button { font-size: 12px; }
.ai-data-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 330px), 1fr)); gap: 18px; align-items: start; }.ai-data-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 20px; min-width: 0; }.ai-data-card header > div:first-of-type { flex: 1; min-width: 0; }.ai-data-card h2 { font-size: 15px; margin: 0; overflow-wrap: anywhere; }.ai-data-card small { display: block; font-size: 11px; color: var(--muted); margin-top: 5px; }.ai-card-actions { gap: 4px; }.ai-card-actions button { padding: 7px; border: 0; color: var(--muted); background: transparent; }.ai-card-actions button:last-child { color: var(--danger); }
dl { margin: 18px 0 0; max-height: 360px; overflow-y: auto; }dl > div { border-top: 1px solid var(--border); padding: 12px 0; }dt { font-size: 11px; color: var(--muted); overflow-wrap: anywhere; }dd { margin: 5px 0 0; font-size: 13px; line-height: 1.6; color: var(--secondary); white-space: pre-wrap; overflow-wrap: anywhere; }
.ai-empty { text-align: center; padding: 48px 20px; color: var(--muted); }.ai-empty h2 { font-size: 18px; color: var(--secondary); }.ai-empty p { font-size: 13px; }.ai-empty button { margin: 18px auto 0; }.ai-notice { color: var(--theme-success, #538c72); font-size: 13px; }
.ai-data-editor { width: min(820px, 100%); max-height: 90dvh; padding: 0; display: flex; flex-direction: column; overflow: hidden; }.ai-data-editor > header { padding: 20px 24px; border-bottom: 1px solid var(--border); flex-shrink: 0; }.ai-data-editor header h2 { font-size: 20px; margin: 0; }.ai-data-editor header p { font-size: 12px; color: var(--muted); margin: 6px 0 0; }.ai-data-editor form { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }.ai-form-scroll { padding: 20px 24px; overflow-y: auto; min-height: 0; }.ai-field-help { font-size: 12px; line-height: 1.6; color: var(--muted); margin: 18px 0; }.ai-field-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) auto; gap: 12px; padding: 14px 0; border-top: 1px solid var(--border); align-items: start; }.ai-field-row label { font-size: 12px; color: var(--secondary); }.ai-field-row textarea { resize: vertical; font-size: 13px; }.ai-field-row > button { margin-top: 26px; }.ai-data-editor footer { padding: 16px 24px; border-top: 1px solid var(--border); flex-shrink: 0; margin: 0; }.ai-delete-dialog { width: min(480px, 100%); }.ai-delete-dialog h2 { font-size: 18px; overflow-wrap: anywhere; }.ai-delete-dialog p { font-size: 13px; color: var(--muted); }.ai-delete-button { color: var(--theme-danger, #bb3549); border-color: var(--theme-danger-border, #f1d6dc); }
@media (max-width: 600px) { .ai-field-row { grid-template-columns: minmax(0, 1fr) auto; }.ai-field-row label:nth-child(2) { grid-column: 1; }.ai-field-row > button { grid-column: 2; grid-row: 1; }.ai-data-editor > header, .ai-form-scroll, .ai-data-editor footer { padding: 16px; } }
</style>
