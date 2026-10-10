<script setup>
import { ref } from 'vue'
import { FileSpreadsheet, Upload, Download, X, Check } from 'lucide-vue-next'
const props = defineProps({ api: Function, dictionary: Object, disabled: Boolean, compact: Boolean })
const emit = defineEmits(['imported'])
const picker = ref(null), busy = ref(false), error = ref(''), notice = ref(''), preview = ref(null)
async function choose(file) {
  if (!file || busy.value || props.disabled) return
  error.value = ''; notice.value = ''; preview.value = null
  if (!file.name.toLowerCase().endsWith('.xlsx')) { error.value = 'Wybierz plik Excel w formacie .xlsx.'; return }
  if (!file.size || file.size > 10 * 1024 * 1024) { error.value = 'Wybierz niepusty plik o rozmiarze do 10 MB.'; return }
  busy.value = true
  try {
    const body = new FormData(); body.append('file', file)
    preview.value = await props.api(`/dictionaries/${props.dictionary.id}/excel/preview`, 'POST', body)
  } catch (err) { error.value = err.message }
  finally { busy.value = false; if (picker.value) picker.value.value = '' }
}
async function commit() {
  if (busy.value || !preview.value || props.disabled) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api(`/dictionaries/${props.dictionary.id}/excel/import`, 'POST', { version: preview.value.version, rows: preview.value.rows })
    preview.value = null; notice.value = `Dodano ${result.imported} wpisów z Excela.`; emit('imported')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="excel-transfer" :class="{ compact }">
    <div class="excel-buttons"><a :href="!disabled && !busy ? `/api/dictionaries/${dictionary.id}/excel` : null" :aria-disabled="disabled || busy" class="excel-export"><Download :size="16" /> Eksport Excel</a><button :disabled="disabled || busy" @click="picker.click()"><Upload :size="16" /> {{ busy ? 'Wczytywanie…' : 'Import Excel' }}</button><input ref="picker" class="file-picker" type="file" accept=".xlsx" aria-label="Plik Excel do importu" @change="choose($event.target.files[0])" /></div>
    <p v-if="error && !preview" class="error" role="alert">{{ error }}</p><p v-if="notice" class="excel-notice" role="status">{{ notice }}</p>
  </div>
  <div v-if="preview" class="modal-backdrop"><section class="panel excel-dialog" role="dialog" aria-modal="true" aria-labelledby="excel-import-title"><header class="editor-heading"><div><h2 id="excel-import-title"><FileSpreadsheet :size="21" /> Import do „{{ dictionary.name }}”</h2><p>Arkusz: {{ preview.sheet }} · {{ preview.count }} wpisów</p></div><button class="icon-button" :disabled="busy" aria-label="Zamknij import" @click="preview = null"><X :size="20" /></button></header><div class="excel-preview"><p>Import doda nowe wpisy. Dotychczasowe dane pozostaną zachowane.</p><p v-if="error" class="error" role="alert">{{ error }}</p><div class="excel-table"><table><thead><tr><th v-for="field in preview.fields" :key="field">{{ field }}</th></tr></thead><tbody><tr v-for="(row, index) in preview.rows.slice(0, 10)" :key="index"><td v-for="field in preview.fields" :key="field">{{ row[field] || '—' }}</td></tr></tbody></table></div><p v-if="preview.count > 10" class="muted">Podgląd pierwszych 10 wpisów. Zaimportowanych zostanie {{ preview.count }}.</p></div><footer class="editor-actions"><button :disabled="busy" @click="preview = null">Anuluj</button><button class="primary" :disabled="busy || disabled" @click="commit"><Check :size="16" /> {{ busy ? 'Importowanie…' : `Importuj ${preview.count} wpisów` }}</button></footer></section></div>
</template>

<style scoped>
.excel-transfer { margin: 12px 0 20px; }.excel-transfer.compact { margin: 0; }.excel-buttons { display: flex; flex-direction: row; gap: 8px; flex-wrap: nowrap; align-items: center; }.excel-buttons button, .excel-export { font-size: 12px; white-space: nowrap; flex: 0 0 auto; height: 38px; box-sizing: border-box; }.excel-export { display: inline-flex; align-items: center; gap: 7px; padding: 10px 14px; border: 1px solid var(--border); background: var(--surface); border-radius: 8px; color: var(--secondary); text-decoration: none; }.excel-export:hover { color: var(--accent); background: var(--accent-soft); }.excel-export[aria-disabled='true'] { opacity: .5; pointer-events: none; }.excel-notice { color: var(--success); font-size: 12px; }.excel-transfer .error { font-size: 12px; }
.excel-dialog { width: min(960px, 100%); max-height: 90dvh; display: flex; flex-direction: column; padding: 0; overflow: hidden; }.excel-dialog header { padding: 20px 24px; margin: 0; border-bottom: 1px solid var(--border); flex-shrink: 0; }.excel-dialog h2 { display: flex; align-items: center; gap: 10px; font-size: 18px; margin: 0; }.excel-dialog header p { color: var(--muted); font-size: 12px; margin: 6px 0 0; }.excel-preview { padding: 18px 24px; overflow-y: auto; min-height: 0; }.excel-preview > p { font-size: 12px; color: var(--muted); line-height: 1.6; }.excel-table { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }table { width: 100%; border-collapse: collapse; font-size: 12px; }th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid var(--border); min-width: 100px; max-width: 350px; overflow-wrap: anywhere; white-space: pre-wrap; }th { color: var(--muted); background: var(--surface-soft); white-space: nowrap; }.excel-dialog footer { padding: 16px 24px; margin: 0; border-top: 1px solid var(--border); flex-shrink: 0; }
</style>
