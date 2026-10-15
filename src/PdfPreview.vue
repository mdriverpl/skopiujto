<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { X, Download, RefreshCw, FileText } from 'lucide-vue-next'

const props = defineProps({ file: { type: Object, required: true }, accountId: String })
const emit = defineEmits(['close'])
const dialog = ref(null), source = ref(''), loading = ref(true), error = ref('')
const downloadUrl = computed(() => `/api/documents/${encodeURIComponent(props.file.id)}/file`)
let controller, generation = 0
function release() { if (source.value) URL.revokeObjectURL(source.value); source.value = '' }
async function load() {
  const request = ++generation
  controller?.abort()
  controller = new AbortController()
  release(); loading.value = true; error.value = ''
  try {
    const response = await fetch(`/api/documents/${encodeURIComponent(props.file.id)}/preview?v=${encodeURIComponent(props.file.version ?? '')}`, {
      credentials: 'same-origin', signal: controller.signal,
      headers: props.accountId ? { 'X-Account-ID': props.accountId } : {}
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      throw new Error(typeof data?.detail === 'string' ? data.detail : 'Nie udało się otworzyć pliku PDF.')
    }
    if (!response.headers.get('content-type')?.includes('application/pdf')) throw new Error('Ten plik nie jest dostępny jako PDF.')
    const blob = await response.blob()
    if (request !== generation) return
    source.value = URL.createObjectURL(blob)
  } catch (err) {
    if (request === generation && err.name !== 'AbortError') error.value = err.message || 'Nie udało się pobrać pliku PDF.'
  } finally { if (request === generation) loading.value = false }
}
watch(() => [props.file.id, props.file.version, props.accountId], load, { immediate: true })
onMounted(() => dialog.value?.showModal())
onBeforeUnmount(() => { generation++; controller?.abort(); release() })
</script>

<template>
  <dialog ref="dialog" class="pdf-preview-dialog" aria-labelledby="pdf-preview-title" @cancel.prevent="emit('close')">
    <header><div class="pdf-preview-heading"><FileText :size="22" /><div><h2 id="pdf-preview-title">{{ file.title || file.filename }}</h2><small>{{ file.filename }} · Podgląd PDF</small></div></div><div class="pdf-preview-actions"><a :href="downloadUrl" class="pdf-download" title="Pobierz plik PDF" aria-label="Pobierz plik PDF"><Download :size="19" /><span>Pobierz</span></a><button type="button" title="Zamknij podgląd PDF" aria-label="Zamknij podgląd PDF" @click="emit('close')"><X :size="21" /></button></div></header>
    <div v-if="loading" class="pdf-preview-state" role="status">Wczytywanie pliku PDF…</div>
    <div v-else-if="error" class="pdf-preview-state"><p role="alert">{{ error }}</p><button @click="load"><RefreshCw :size="17" /> Spróbuj ponownie</button></div>
    <iframe v-else-if="source" :src="`${source}#view=FitH`" :title="`Podgląd PDF: ${file.filename}`" class="pdf-preview-frame"></iframe>
    <footer>Jeśli przeglądarka nie wyświetla podglądu, użyj przycisku „Pobierz”.</footer>
  </dialog>
</template>

<style scoped>
.pdf-preview-dialog { width:min(1200px,96vw); height:92dvh; max-width:96vw; max-height:94dvh; margin:auto; padding:0; border:1px solid var(--border); border-radius:16px; background:var(--surface); color:var(--text); box-shadow:0 25px 90px #0004; overflow:hidden; }
.pdf-preview-dialog[open] { display:flex; flex-direction:column; }.pdf-preview-dialog::backdrop { background:#13213988; backdrop-filter:blur(3px); }
header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 20px; border-bottom:1px solid var(--border); flex-shrink:0; }.pdf-preview-heading { display:flex; align-items:center; gap:12px; min-width:0; }.pdf-preview-heading > svg { flex-shrink:0; color:var(--accent); }.pdf-preview-heading > div { min-width:0; }h2 { font-size:16px; margin:0 0 5px; overflow-wrap:anywhere; }small { color:var(--secondary); font-size:11px; overflow-wrap:anywhere; }
.pdf-preview-actions { display:flex; align-items:center; gap:10px; flex-shrink:0; }.pdf-preview-actions button { padding:8px; }.pdf-download { display:inline-flex; align-items:center; gap:7px; padding:8px; font-size:12px; text-decoration:none; }
.pdf-preview-frame { flex:1; min-height:0; width:100%; border:0; background:#525659; }.pdf-preview-state { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:16px; padding:24px; text-align:center; color:var(--secondary); }footer { padding:9px 20px; font-size:11px; color:var(--secondary); border-top:1px solid var(--border); flex-shrink:0; }
@media(max-width:650px) { .pdf-preview-dialog { width:100vw; max-width:100vw; height:100dvh; max-height:100dvh; border:0; border-radius:0; }header { padding:12px; gap:8px; }h2 { font-size:14px; }.pdf-download span { display:none; }footer { padding:9px 12px; } }
</style>
