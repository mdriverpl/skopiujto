<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { FileText, Pencil, ClipboardList, RotateCcw } from 'lucide-vue-next'
import RichTextEditor from './RichTextEditor.vue'
import { documentFields, documentText, fillDocument, plainDocument } from './documentFields.js'

const props = defineProps({ modelValue: Object, plainText: String, fieldSource: Object, fieldValues: Object, editable: Boolean, api: Function, title: String, documentId: String })
const emit = defineEmits(['update:modelValue', 'update:plainText', 'update:fieldSource', 'update:fieldValues'])
const source = ref(JSON.parse(JSON.stringify(props.fieldSource || props.modelValue || plainDocument(props.plainText))))
const values = ref({ ...props.fieldValues })
const fields = computed(() => documentFields(source.value))
const mode = ref(fields.value.length ? 'fill' : 'edit')
const result = computed(() => fillDocument(source.value, values.value))
const completed = computed(() => fields.value.filter(field => values.value[field.key]?.trim()).length)
const memoryStatus = ref('')
const memoryError = ref('')
const matchError = ref('')
const matching = ref(false)
const autoSources = ref({})
const manualValues = { ...props.fieldValues }
const touched = new Set()
const memoryKey = props.documentId || crypto.randomUUID()
let saveTimer, matchTimer, savingPromise, dirty = false, disposed = false, revision = 0
function context() { return documentText(source.value).slice(0, 40000) }
function invalidateAutomatic(exceptKey) {
  const next = { ...values.value }
  for (const key of Object.keys(autoSources.value)) {
    if (key !== exceptKey) delete next[key]
  }
  autoSources.value = {}; values.value = next
}
function recordManual(key) {
  if (!props.editable) return
  touched.add(key); revision++
  manualValues[key] = values.value[key] || ''
  invalidateAutomatic(key)
  dirty = true
  memoryStatus.value = 'Zapamiętywanie danych…'
  clearTimeout(saveTimer); clearTimeout(matchTimer)
  saveTimer = setTimeout(flushMemory, 800)
  matchTimer = setTimeout(matchFields, 1500)
}
function flushMemory() {
  if (savingPromise) return savingPromise
  if (!props.api || !dirty) return Promise.resolve()
  savingPromise = (async () => {
    while (dirty) {
      const known = new Set(fields.value.map(field => field.key))
      const data = Object.fromEntries(Object.entries(manualValues).filter(([key, value]) => known.has(key) && value.trim()))
      dirty = false
      if (!Object.keys(data).length) { memoryStatus.value = ''; continue }
      try {
        await props.api('/saved-data/remember', 'POST', { source_key: memoryKey,
          name: `Dane: ${props.title || 'Dokument'}`.slice(0, 100), fields: data, context: context() })
        memoryError.value = ''
        memoryStatus.value = 'Dane zapamiętane automatycznie.'
      } catch (error) {
        dirty = true
        memoryError.value = `Nie zapisano danych do pamięci: ${error.message}`
        memoryStatus.value = ''
        break
      }
    }
  })().finally(() => { savingPromise = null })
  return savingPromise
}
async function matchFields() {
  if (!props.api || !props.editable || disposed) return
  if (matching.value) { clearTimeout(matchTimer); matchTimer = setTimeout(matchFields, 1500); return }
  const empty = fields.value.filter(field => !values.value[field.key]?.trim() && !touched.has(field.key))
  if (!empty.length) return
  const requestRevision = revision
  const requestSource = context()
  const requestTitle = props.title || ''
  matching.value = true; matchError.value = ''
  try {
    const response = await props.api('/saved-data/match', 'POST', {
      title: requestTitle, context: requestSource, fields: empty.map(field => field.label),
      values: Object.fromEntries(fields.value.filter(field => values.value[field.key]?.trim()).map(field => [field.key, values.value[field.key]])),
    })
    if (disposed || !props.editable || revision !== requestRevision || requestSource !== context() || requestTitle !== (props.title || '')) return
    const allowed = new Set(empty.map(field => field.key))
    const next = { ...values.value }
    for (const [key, match] of Object.entries(response.matches || {})) {
      if (allowed.has(key) && !next[key]?.trim() && !touched.has(key) && typeof match.value === 'string') {
        Object.defineProperty(next, key, { value: match.value, enumerable: true, configurable: true, writable: true })
        autoSources.value[key] = match.source
      }
    }
    values.value = next
  } catch (error) { if (!disposed) matchError.value = error.message }
  finally { matching.value = false }
}
function clearFields() {
  if (!props.editable) return
  for (const field of fields.value) { touched.add(field.key); delete manualValues[field.key] }
  revision++; values.value = {}; autoSources.value = {}
}
defineExpose({ flushMemory })
function publish() {
  if (!props.editable) return
  const validKeys = new Set(fields.value.map(field => field.key))
  const currentValues = Object.fromEntries(Object.entries(values.value).filter(([key]) => validKeys.has(key)))
  emit('update:modelValue', fillDocument(source.value, currentValues))
  emit('update:plainText', documentText(fillDocument(source.value, currentValues)))
  emit('update:fieldSource', fields.value.length ? source.value : null)
  emit('update:fieldValues', fields.value.length ? currentValues : {})
}
watch([source, values], publish, { deep: true })
watch([source, () => props.title], () => {
  revision++; invalidateAutomatic(); clearTimeout(matchTimer); matchTimer = setTimeout(matchFields, 1500)
}, { deep: true })
onMounted(() => { if (fields.value.length) publish(); matchFields() })
onBeforeUnmount(() => { disposed = true; clearTimeout(saveTimer); clearTimeout(matchTimer); flushMemory() })
</script>

<template>
  <section class="document-composer">
    <div v-if="fields.length" class="composer-toolbar"><div class="composer-tabs" role="group" aria-label="Widok dokumentu"><button type="button" :aria-pressed="mode === 'fill'" @click="mode = 'fill'"><FileText :size="15" /> Podgląd i dane</button><button v-if="editable" type="button" :aria-pressed="mode === 'edit'" @click="mode = 'edit'"><Pencil :size="15" /> Edytuj treść wzoru</button></div><span>{{ completed }} / {{ fields.length }} pól uzupełnionych</span></div>
    <div v-if="mode === 'fill' && fields.length" class="composer-columns">
      <div class="contract-preview" tabindex="0" role="region" aria-label="Przewijana treść dokumentu"><RichTextEditor :model-value="result" :plain-text="documentText(result)" :editable="false" label="Podgląd dokumentu" /></div>
      <aside class="contract-fields" tabindex="0" aria-label="Dane do dokumentu"><header><ClipboardList :size="18" /><div><h3>Uzupełnij dane</h3><p>Zmiany od razu pojawią się w treści.</p></div></header>
        <p v-if="editable && api" class="memory-status" role="status">{{ matching ? 'AI sprawdza pasujące dane…' : memoryStatus || 'Wpisane dane zapamiętujemy automatycznie. AI uzupełnia pasujące puste pola.' }}</p>
        <p v-if="memoryError || matchError" class="memory-status memory-error" role="alert">{{ memoryError || matchError }}</p>
        <label v-for="field in fields" :key="field.key">{{ field.label }}<input v-model="values[field.key]" :readonly="!editable" maxlength="2000" :placeholder="`Wpisz: ${field.label}`" @input="recordManual(field.key)" /><small v-if="autoSources[field.key]" class="ai-field-source">Uzupełnione przez AI · {{ autoSources[field.key] }}</small></label>
        <p class="fields-note">Puste pola pozostają oznaczone nawiasami w dokumencie.</p>
        <button v-if="editable && completed" type="button" class="clear-fields" @click="clearFields"><RotateCcw :size="14" /> Wyczyść dane</button>
      </aside>
    </div>
    <div v-else class="composer-edit-content"><p v-if="editable" class="pattern-hint">Pola do wypełnienia zapisuj w nawiasach, np. [imię sprzedającego] lub [cena].</p><RichTextEditor v-model="source" :plain-text="plainText" :editable="editable" /></div>
  </section>
</template>

<style scoped>
.document-composer { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
.composer-toolbar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; flex-shrink: 0; }
.composer-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.composer-tabs button { font-size: 12px; border: none; padding: 8px 11px; color: var(--muted); }
.composer-tabs button[aria-pressed='true'] { color: var(--accent); background: var(--accent-soft); }
.composer-toolbar > span { font-size: 11px; color: var(--muted); }
.composer-columns { display: grid; grid-template-columns: minmax(0, 1fr) 300px; grid-template-rows: minmax(0, 1fr); gap: 22px; flex: 1; min-height: 0; }
.contract-preview, .contract-fields, .composer-edit-content { overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; min-height: 0; }
.contract-preview:focus-visible, .contract-fields:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.composer-edit-content { flex: 1; }
.contract-preview { background: var(--surface); padding: 24px 32px; border: 1px solid var(--border); border-radius: 10px; min-width: 0; }
.contract-fields { background: var(--surface-soft); border: 1px solid var(--border); border-radius: 12px; padding: 20px; min-width: 0; }
.contract-fields header { display: flex; gap: 10px; color: var(--accent); margin-bottom: 22px; }
h3 { margin: 0; color: var(--secondary); font-size: 14px; }
.contract-fields header p { color: var(--muted); font-size: 11px; line-height: 1.6; margin: 6px 0 0; }
.contract-fields label { color: var(--secondary); font-size: 12px; margin-top: 16px; overflow-wrap: anywhere; }
.contract-fields input { font-size: 13px; }
.fields-note, .pattern-hint { font-size: 11px; color: var(--muted); line-height: 1.7; }
.fields-note { margin: 20px 0 0; }
.clear-fields { font-size: 11px; margin-top: 16px; padding: 0; color: var(--muted); border: none; background: transparent; }
.memory-status { font-size: 11px; color: var(--accent); line-height: 1.6; margin: 0 0 18px; }
.memory-error { color: var(--danger); }
.ai-field-source { color: var(--accent); font-size: 10px; line-height: 1.6; }
@media (max-width: 800px) { .composer-columns { grid-template-columns: 1fr; grid-template-rows: repeat(2, minmax(0, 1fr)); gap: 12px; } .contract-preview { padding: 16px 20px; } }
</style>
