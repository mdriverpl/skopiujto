<script setup>
import { onMounted, ref } from 'vue'
import { Sparkles, Upload, FileText, X } from 'lucide-vue-next'

const props = defineProps({ api: Function, kind: { type: String, default: 'document' }, folderId: { type: String, default: null } })
const emit = defineEmits(['generated', 'busy'])
const prompt = ref(''), busy = ref(false), checking = ref(true), available = ref(false), error = ref('')
const sourceFile = ref(null), sourceInput = ref(null)
const accepted = ['pdf', 'doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'png', 'jpg', 'jpeg', 'webp']
function selectFile(event) {
  if (busy.value) return
  const file = event.target.files?.[0]
  sourceFile.value = null
  if (!file) return
  if (!accepted.includes(file.name.split('.').pop().toLowerCase())) {
    error.value = 'Wybierz dokument PDF, Word, ODT, RTF, TXT/MD lub skan PNG/JPG/WEBP.'
    event.target.value = ''; return
  }
  if (!file.size || file.size > 10 * 1024 * 1024) {
    error.value = file.size ? 'Maksymalny rozmiar pliku to 10 MB.' : 'Wybrany plik jest pusty.'
    event.target.value = ''; return
  }
  sourceFile.value = file; error.value = ''
}
function clearFile() { sourceFile.value = null; if (sourceInput.value) sourceInput.value.value = '' }
onMounted(async () => {
  try { const config = await props.api('/ai/config'); available.value = config.available; error.value = config.message }
  catch (err) { error.value = err.message }
  finally { checking.value = false }
})
async function generate() {
  if (busy.value || !available.value || (!prompt.value.trim() && !(props.kind === 'template' && sourceFile.value))) return
  busy.value = true; error.value = ''; emit('busy', true)
  try {
    let draft
    if (props.kind === 'template' && sourceFile.value) {
      const form = new FormData()
      form.append('file', sourceFile.value)
      form.append('prompt', prompt.value)
      draft = await props.api('/ai/templates/from-file', 'POST', form)
    } else {
      draft = await props.api('/ai/generate', 'POST', { prompt: prompt.value, kind: props.kind, folder_id: props.folderId })
    }
    emit('generated', draft)
  } catch (err) { error.value = err.message }
  finally { busy.value = false; emit('busy', false) }
}
</script>

<template>
  <section class="ai-prompt">
    <label>Prompt — opisz {{ kind === 'template' ? 'szablon' : 'dokument' }}<textarea v-model="prompt" :disabled="busy" rows="5" maxlength="8000" :placeholder="kind === 'template' ? 'Np. Szablon protokołu spotkania: uczestnicy, ustalenia, zadania i podpisy. Pozostaw pola do uzupełnienia.' : 'Np. Przygotuj ofertę wykonania strony internetowej. Uwzględnij zakres prac, harmonogram i warunki płatności.'"></textarea></label>
    <div v-if="kind === 'template'" class="source-file-section">
      <span class="source-label">Plik źródłowy (opcjonalnie)</span>
      <input ref="sourceInput" class="source-picker" type="file" accept=".pdf,.doc,.docx,.odt,.rtf,.txt,.md,.png,.jpg,.jpeg,.webp" :disabled="busy" aria-label="Wybierz plik do utworzenia szablonu" @change="selectFile" />
      <div v-if="sourceFile" class="source-selected"><FileText :size="19" /><div><strong>{{ sourceFile.name }}</strong><span>{{ (sourceFile.size / 1024).toLocaleString('pl-PL', { maximumFractionDigits: 0 }) }} KB · materiał do szablonu</span></div><button type="button" class="icon-button" :disabled="busy" aria-label="Usuń wybrany plik" @click="clearFile"><X :size="17" /></button></div>
      <button v-else type="button" class="source-upload" :disabled="busy" @click="sourceInput.click()"><Upload :size="18" /><div><strong>Załaduj dokument lub skan</strong><span>PDF, Word, ODT, RTF, TXT/MD, PNG/JPG/WEBP · do 10 MB</span></div></button>
      <p class="ai-hint">Na podstawie pliku AI przygotuje wzór z polami do uzupełnienia. Prompt może pozostać pusty lub zawierać dodatkowe wskazówki.</p>
    </div>
    <p class="ai-hint">{{ sourceFile ? 'Opis i wybrany plik zostaną wysłane do OpenAI.' : 'Opis zostanie wysłany do OpenAI.' }} Wygenerowaną treść otworzysz w edytorze i zapiszesz po sprawdzeniu.</p>
    <p v-if="error" class="ai-error" role="alert">{{ error }}</p>
    <div class="ai-actions"><span>{{ prompt.length }} / 8000</span><button type="button" class="primary" :disabled="checking || !available || busy || (!prompt.trim() && !(kind === 'template' && sourceFile))" @click="generate"><Sparkles :size="16" /> {{ busy ? 'Generowanie…' : checking ? 'Sprawdzanie…' : sourceFile ? 'Utwórz szablon z pliku' : 'Generuj z OpenAI' }}</button></div>
    <p v-if="busy" class="ai-hint" role="status">Tworzenie treści może potrwać chwilę.</p>
  </section>
</template>

<style scoped>
.ai-prompt { margin-top: 22px; }
label { font-size: 12px; color: var(--secondary); }
textarea { font-size: 13px; line-height: 1.7; min-height: 125px; }
.ai-hint { font-size: 11px; color: var(--muted); line-height: 1.7; margin: 10px 0; }
.ai-error { font-size: 12px; color: var(--danger); background: var(--danger-soft); border: 1px solid var(--theme-danger-border, #f0dada); border-radius: 8px; padding: 12px; line-height: 1.6; }
.ai-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 14px; }
.ai-actions span { font-size: 10px; color: var(--muted); }
.ai-actions button { font-size: 12px; }
.source-file-section { margin: 18px 0; }
.source-label { display: block; font-size: 12px; color: var(--secondary); margin-bottom: 9px; }
.source-picker { display: none; }
.source-upload, .source-selected { display: flex; align-items: center; gap: 12px; width: 100%; padding: 16px; border: 1px dashed var(--theme-border, #d9d1ee); border-radius: 10px; background: var(--theme-accent-soft, #faf8ff); color: var(--accent); text-align: left; }
.source-upload > div, .source-selected > div { flex: 1; min-width: 0; }
.source-upload strong, .source-selected strong { display: block; font-size: 12px; font-weight: 500; overflow-wrap: anywhere; }
.source-upload span, .source-selected span { display: block; font-size: 10px; line-height: 1.7; color: var(--muted); margin-top: 4px; }
.source-selected { border-style: solid; }
.source-selected > svg { flex-shrink: 0; }
</style>
