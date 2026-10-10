<script setup>
import { computed, onMounted, ref } from 'vue'
import { BookOpen, Sparkles, Plus, ArrowLeft, ArrowUpRight, Search, Pencil, Trash2, X, Save, RefreshCw } from 'lucide-vue-next'
import AiDataPanel from './AiDataPanel.vue'
import ExcelTransfer from './ExcelTransfer.vue'
import { fieldKey } from './documentFields.js'

const props = defineProps({ api: Function })
const dictionaries = ref([]), selected = ref(null), entries = ref([]), search = ref('')
const busy = ref(false), error = ref(''), formError = ref(''), draft = ref(null), record = ref(null)
const aiCount = ref(0)
const aiRevision = ref(0)
async function imported() {
  if (selected.value?.id === 'ai') { aiRevision.value++; return }
  if (selected.value) await open(selected.value)
}
const removedFields = computed(() => draft.value?.id ? draft.value.originalFields.filter(field => !draft.value.sources.includes(field)) : [])
const filtered = computed(() => entries.value.filter(entry => Object.values(entry.values).join(' ').toLocaleLowerCase('pl').includes(search.value.trim().toLocaleLowerCase('pl'))))
async function load() {
  busy.value = true; error.value = ''
  try {
    const [list, saved] = await Promise.all([props.api('/dictionaries'), props.api('/saved-data')])
    dictionaries.value = list; aiCount.value = saved.reduce((count, item) => count + Object.keys(item.fields).length, 0)
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function open(item) {
  if (busy.value) return
  error.value = ''; search.value = ''
  if (item.id === 'ai') { selected.value = item; return }
  busy.value = true
  try { const result = await props.api(`/dictionaries/${item.id}/entries`); entries.value = result.entries; selected.value = result.dictionary }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function back() { if (busy.value) return; selected.value = null; entries.value = []; search.value = ''; await load() }
function newDictionary() { if (!busy.value) { draft.value = { name: '', fields: ['Imię', 'Nazwisko', 'Stanowisko', 'Telefon', 'E-mail'] }; formError.value = '' } }
function editDictionary(item) {
  if (busy.value || item.id === 'ai') return
  draft.value = { id: item.id, version: item.version, name: item.name, originalName: item.name, fields: [...item.fields], sources: [...item.fields], originalFields: [...item.fields] }
  formError.value = ''
}
function removeField(index) {
  if (busy.value || !draft.value || draft.value.fields.length === 1) return
  draft.value.fields.splice(index, 1)
  draft.value.sources?.splice(index, 1)
}
function addField() {
  if (busy.value || !draft.value || draft.value.fields.length >= 60) return
  draft.value.fields.push(''); draft.value.sources?.push(null)
}
async function saveDictionary() {
  if (busy.value || !draft.value) return
  formError.value = ''; busy.value = true
  try {
    const item = draft.value
    if (!item.name.trim()) throw new Error('Podaj nazwę słownika.')
    const names = item.fields.map(field => field.trim())
    if (names.some(field => !field)) throw new Error('Uzupełnij nazwę każdego pola lub usuń puste pole.')
    if (new Set(names.map(fieldKey)).size !== names.length) throw new Error('Nazwy pól nie mogą się powtarzać.')
    if (item.id && !Number.isInteger(item.version)) {
      const current = await props.api(`/dictionaries/${item.id}/entries`)
      if (JSON.stringify(current.dictionary.fields) !== JSON.stringify(item.originalFields) || current.dictionary.name !== item.originalName)
        throw new Error('Słownik został zmieniony. Zamknij edycję i odśwież listę przed ponowną próbą.')
      item.version = current.dictionary.version
    }
    if (removedFields.value.length && !window.confirm(`Usunąć pola: ${removedFields.value.join(', ')}? Ich wartości zostaną usunięte ze wszystkich wpisów.`)) return
    const result = await props.api(item.id ? `/dictionaries/${item.id}` : '/dictionaries', item.id ? 'PUT' : 'POST', {
      name: item.name, fields: item.fields.map(field => field.trim()),
      ...(item.id ? { version: item.version, field_sources: Object.fromEntries(item.fields.map((field, index) => [field.trim(), item.sources[index]])) } : {}) })
    const saved = item.id ? result.dictionary : result
    dictionaries.value = [...dictionaries.value.filter(entry => entry.id !== saved.id), saved]
    draft.value = null; selected.value = saved; entries.value = item.id ? result.entries : []; search.value = ''
  } catch (err) { formError.value = err.message }
  finally { busy.value = false }
}
function editRecord(item = null) {
  if (busy.value || !selected.value || selected.value.id === 'ai') return
  record.value = { id: item?.id, version: item?.version, values: Object.fromEntries(selected.value.fields.map(field => [field, item?.values[field] || ''])) }
  formError.value = ''
}
async function saveRecord() {
  if (busy.value || !record.value) return
  busy.value = true; formError.value = ''
  try {
    const item = record.value
    const saved = await props.api(`/dictionaries/${selected.value.id}/entries${item.id ? '/' + item.id : ''}`, item.id ? 'PUT' : 'POST', { values: item.values, ...(item.id ? { version: item.version } : {}) })
    entries.value = [saved, ...entries.value.filter(entry => entry.id !== saved.id)]
    selected.value.count = entries.value.length; record.value = null
  } catch (err) { formError.value = err.message }
  finally { busy.value = false }
}
async function removeRecord(item) {
  if (busy.value || !window.confirm('Usunąć ten wpis ze słownika?')) return
  busy.value = true; error.value = ''
  try { await props.api(`/dictionaries/${selected.value.id}/entries/${item.id}`, 'DELETE'); entries.value = entries.value.filter(entry => entry.id !== item.id); selected.value.count = entries.value.length }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function removeDictionary(item) {
  if (busy.value || !window.confirm(`Usunąć słownik „${item.name}” wraz z jego wpisami?`)) return
  busy.value = true; error.value = ''
  try { await props.api(`/dictionaries/${item.id}`, 'DELETE'); dictionaries.value = dictionaries.value.filter(entry => entry.id !== item.id) }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <section class="dictionaries-panel">
    <button v-if="selected" class="dictionary-back" :disabled="busy" @click="back"><ArrowLeft :size="16" /> Słowniki</button>
    <template v-if="selected?.id === 'ai'"><AiDataPanel :key="aiRevision" :api="api"><template #actions><ExcelTransfer compact :key="selected.id" :api="api" :dictionary="selected" :disabled="busy" @imported="imported" /></template></AiDataPanel></template>
    <template v-else>
      <header class="dictionary-heading"><div><h1>{{ selected?.name || 'Słowniki' }}</h1><p>{{ selected ? `${entries.length} wpisów · ${selected.fields.length} pól` : 'Zapisane dane AI i własne listy danych.' }}</p></div><div class="dictionary-heading-actions"><ExcelTransfer v-if="selected" compact :key="selected.id" :api="api" :dictionary="selected" :disabled="busy" @imported="imported" /><button v-if="selected" :disabled="busy" @click="editDictionary(selected)"><Pencil :size="16" /> Edytuj słownik</button><button class="icon-button" :disabled="busy" title="Odśwież" aria-label="Odśwież słowniki" @click="selected ? open(selected) : load()"><RefreshCw :size="17" /></button><button class="primary" :disabled="busy" @click="selected ? editRecord() : newDictionary()"><Plus :size="17" /> {{ selected ? 'Dodaj wpis' : 'Dodaj słownik' }}</button></div></header>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="busy && !draft && !record" class="muted" role="status">Wczytywanie…</p>
      <div v-if="!selected" class="dictionary-tiles">
        <button class="dictionary-tile ai-tile" :disabled="busy" @click="open({ id: 'ai', name: 'AI' })"><span class="dictionary-icon"><Sparkles :size="26" /></span><strong>AI</strong><p>Dane zapisywane automatycznie podczas uzupełniania dokumentów.</p><footer><span>{{ aiCount }} zapisanych pól</span><ArrowUpRight :size="18" /></footer></button>
        <article v-for="item in dictionaries" :key="item.id" class="dictionary-tile"><button class="dictionary-open" :disabled="busy" @click="open(item)"><span class="dictionary-icon"><BookOpen :size="26" /></span><strong>{{ item.name }}</strong><p>{{ item.fields.join(' · ') }}</p></button><footer><span>{{ item.count }} wpisów · {{ item.fields.length }} pól</span><div class="dictionary-tile-actions"><button class="icon-button" :disabled="busy" :aria-label="`Edytuj słownik ${item.name}`" title="Edytuj słownik" @click="editDictionary(item)"><Pencil :size="16" /></button><button class="icon-button" :disabled="busy" :aria-label="`Usuń słownik ${item.name}`" @click="removeDictionary(item)"><Trash2 :size="16" /></button></div></footer></article>
      </div>
      <template v-else>
        <div class="search dictionary-search"><Search :size="17" /><input v-model="search" placeholder="Szukaj w słowniku…" aria-label="Szukaj wpisu w słowniku" /></div>
        <div class="dictionary-table panel"><table><thead><tr><th v-for="field in selected.fields" :key="field">{{ field }}</th><th>Akcje</th></tr></thead><tbody><tr v-for="item in filtered" :key="item.id"><td v-for="field in selected.fields" :key="field">{{ item.values[field] || '—' }}</td><td class="row-actions"><button class="icon-button" :disabled="busy" aria-label="Edytuj wpis" @click="editRecord(item)"><Pencil :size="16" /></button><button class="icon-button" :disabled="busy" aria-label="Usuń wpis" @click="removeRecord(item)"><Trash2 :size="16" /></button></td></tr></tbody></table><p v-if="!filtered.length" class="dictionary-empty">{{ search ? 'Brak pasujących wpisów.' : 'Słownik jest pusty. Dodaj pierwszy wpis.' }}</p></div>
      </template>
    </template>
  </section>
  <div v-if="draft || record" class="modal-backdrop"><section class="panel dictionary-dialog" role="dialog" aria-modal="true" aria-labelledby="dictionary-dialog-title"><header class="editor-heading"><h2 id="dictionary-dialog-title">{{ draft ? (draft.id ? 'Edytuj słownik' : 'Nowy słownik') : record.id ? 'Edytuj wpis' : 'Dodaj wpis' }}</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="draft = null; record = null"><X :size="20" /></button></header><form @submit.prevent="draft ? saveDictionary() : saveRecord()"><div class="dictionary-form"><p v-if="formError" class="error" role="alert">{{ formError }}</p><template v-if="draft"><p v-if="removedFields.length" class="dictionary-warning">Usunięte pola: {{ removedFields.join(', ') }}. Po zapisie ich wartości znikną ze wszystkich wpisów.</p><label>Nazwa słownika<input v-model="draft.name" required maxlength="100" :disabled="busy" placeholder="np. Pracownicy" /></label><p class="muted">Pola będą kolumnami na liście wpisów.</p><div v-for="(_, index) in draft.fields" :key="index" class="dictionary-field"><label><input v-model="draft.fields[index]" placeholder="Nazwa pola" :aria-label="`Nazwa pola ${index + 1}`" required maxlength="80" :disabled="busy" /></label><button class="icon-button" type="button" :disabled="busy || draft.fields.length === 1" :aria-label="`Usuń pole ${index + 1}`" @click="removeField(index)"><Trash2 :size="16" /></button></div><button type="button" :disabled="busy || draft.fields.length >= 60" @click="addField"><Plus :size="16" /> Dodaj pole</button></template><template v-else><label v-for="field in selected.fields" :key="field">{{ field }}<input v-model="record.values[field]" maxlength="2000" :disabled="busy" /></label></template></div><footer class="editor-actions"><button type="button" :disabled="busy" @click="draft = null; record = null">Anuluj</button><button type="submit" class="primary" :disabled="busy"><Save :size="16" /> Zapisz</button></footer></form></section></div>
</template>

<style scoped>
.dictionary-tile-actions { display: flex; align-items: center; gap: 4px; }.dictionary-warning { margin: 0; padding: 12px; background: var(--warning-soft); color: var(--warning); border-radius: 9px; font-size: 12px; line-height: 1.6; }

.dictionary-heading-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.dictionary-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 24px 0; flex-wrap: wrap; }h1 { margin: 0; font-size: 26px; }.dictionary-heading p { font-size: 12px; color: var(--muted); margin: 7px 0 0; }.dictionary-back { border: none; background: transparent; color: var(--accent); padding-left: 0; font-size: 12px; }
.dictionary-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 18px; }.dictionary-tile { display: flex; flex-direction: column; align-items: stretch; text-align: left; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 22px; min-width: 0; }.dictionary-tile strong { display: block; font-size: 16px; margin-top: 17px; overflow-wrap: anywhere; }.dictionary-tile p { color: var(--muted); font-size: 12px; line-height: 1.7; margin: 9px 0 18px; overflow-wrap: anywhere; }.dictionary-icon { display: inline-flex; align-items: center; justify-content: center; width: 56px; height: 56px; border-radius: 14px; color: var(--warning); background: var(--warning-soft); }.ai-tile .dictionary-icon { color: var(--accent); background: var(--accent-soft); }.dictionary-open { display: block; padding: 0; text-align: left; background: transparent; border: none; color: inherit; }.dictionary-open:hover { background: transparent; color: var(--accent); }.dictionary-tile footer { margin-top: auto; display: flex; align-items: center; justify-content: space-between; gap: 10px; border-top: 1px solid var(--border); padding-top: 13px; color: var(--muted); font-size: 11px; }
.dictionary-search { max-width: 550px; margin-bottom: 20px; }.dictionary-table { overflow-x: auto; }table { width: 100%; border-collapse: collapse; font-size: 13px; }th { text-align: left; color: var(--muted); font-size: 11px; background: var(--surface-soft); white-space: nowrap; }th, td { padding: 15px 18px; border-bottom: 1px solid var(--border); }td { min-width: 120px; max-width: 420px; overflow-wrap: anywhere; white-space: pre-wrap; }.row-actions { white-space: nowrap; min-width: 100px; }.row-actions button { display: inline-flex; }.dictionary-empty { text-align: center; padding: 28px; color: var(--muted); font-size: 13px; }
.dictionary-dialog { width: min(620px, 100%); max-height: 90dvh; display: flex; flex-direction: column; padding: 0; overflow: hidden; }.dictionary-dialog header { padding: 20px 24px; flex-shrink: 0; border-bottom: 1px solid var(--border); }.dictionary-dialog h2 { margin: 0; font-size: 19px; }.dictionary-dialog form { min-height: 0; overflow: hidden; display: flex; flex-direction: column; }.dictionary-form { padding: 20px 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; min-height: 0; }.dictionary-form .muted { font-size: 12px; margin: 0; }.dictionary-field { display: flex; align-items: flex-end; gap: 10px; }.dictionary-field label { flex: 1; }.dictionary-dialog footer { margin: 0; padding: 16px 24px; flex-shrink: 0; border-top: 1px solid var(--border); }
</style>
