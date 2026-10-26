<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Upload, ImagePlus, X, Check, AlertCircle } from 'lucide-vue-next'
const props = defineProps({ api: Function, endpoint: String, folderId: String })
const emit = defineEmits(['uploaded', 'close'])
const input = ref(null), queue = ref([]), busy = ref(false), dragging = ref(false)
const dialog = ref(null)
let trigger, previousOverflow
const pending = computed(() => queue.value.filter(item => item.status === 'ready' || item.status === 'error'))
const completed = computed(() => queue.value.filter(item => item.status === 'done').length)
let sequence = 0
function add(files) {
  if (busy.value) return
  for (const file of files || []) {
    const invalid = !/\.(jpe?g|png|webp|gif|bmp|avif|ico)$/i.test(file.name) ? 'Wybierz obsługiwany format zdjęcia.'
      : file.size > 10 * 1024 * 1024 ? 'Zdjęcie przekracza 10 MB.' : !file.size ? 'Ten plik jest pusty.' : ''
    queue.value.push({ id: ++sequence, file, status: invalid ? 'invalid' : 'ready', error: invalid })
  }
}
function picked(event) { add(event.target.files); event.target.value = '' }
function drop(event) { dragging.value = false; add(event.dataTransfer?.files) }
async function upload() {
  if (busy.value || !pending.value.length) return
  busy.value = true
  try {
    for (const item of [...pending.value]) {
      item.status = 'uploading'; item.error = ''
      const body = new FormData(); body.append('file', item.file)
      if (props.folderId) body.append('folder_id', props.folderId)
      try {
        const photo = await props.api(props.endpoint, 'POST', body)
        item.status = 'done'; emit('uploaded', photo)
      } catch (err) { item.status = 'error'; item.error = err.message }
    }
  } finally { busy.value = false }
}
function remove(id) { if (!busy.value) queue.value = queue.value.filter(item => item.id !== id) }
function close() { if (!busy.value) emit('close') }
function keydown(event) {
  if (event.key === 'Escape') { event.preventDefault(); close() }
  if (event.key !== 'Tab') return
  const elements = [...dialog.value.querySelectorAll('button:not(:disabled)')]
  if (event.shiftKey && (document.activeElement === elements[0] || document.activeElement === dialog.value)) { event.preventDefault(); elements.at(-1)?.focus() }
  else if (!event.shiftKey && (document.activeElement === elements.at(-1) || document.activeElement === dialog.value)) { event.preventDefault(); elements[0]?.focus() }
}
onMounted(async () => { trigger = document.activeElement; previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; await nextTick(); dialog.value?.focus() })
onBeforeUnmount(() => { document.body.style.overflow = previousOverflow; if (trigger?.isConnected) trigger.focus() })
</script>
<template>
  <div class="photo-upload-backdrop" @click.self="close" @keydown.stop="keydown">
    <section ref="dialog" class="photo-upload-dialog" role="dialog" aria-modal="true" aria-labelledby="photo-upload-title" tabindex="-1">
      <header><div><h2 id="photo-upload-title"><ImagePlus :size="22" />Dodaj zdjęcia</h2><p>Zdjęcia trafią do aktualnie otwartego katalogu galerii.</p></div><button :disabled="busy" aria-label="Zamknij dodawanie zdjęć" @click="close"><X :size="20" /></button></header>
      <input ref="input" type="file" multiple accept=".jpg,.jpeg,.png,.webp,.gif,.bmp,.avif,.ico" hidden @change="picked" />
      <button class="photo-dropzone" :class="{ dragging }" :disabled="busy" @click="input?.click()" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="drop"><Upload :size="28" /><strong>Wybierz zdjęcia z komputera</strong><span>lub przeciągnij je tutaj · do 10 MB na zdjęcie</span></button>
      <ul v-if="queue.length" class="photo-upload-queue"><li v-for="item in queue" :key="item.id"><Check v-if="item.status === 'done'" :size="17" class="upload-success" /><AlertCircle v-else-if="item.error" :size="17" class="upload-error" /><ImagePlus v-else :size="17" /><div><strong>{{ item.file.name }}</strong><small v-if="item.error" class="upload-error" role="alert">{{ item.error }}</small><small v-else>{{ item.status === 'done' ? 'Dodano do galerii' : item.status === 'uploading' ? 'Przesyłanie…' : `${Math.ceil(item.file.size / 1024)} KB` }}</small></div><button v-if="item.status !== 'done'" :disabled="busy" :aria-label="`Usuń z kolejki: ${item.file.name}`" @click="remove(item.id)"><X :size="16" /></button></li></ul>
      <p class="photo-upload-note">Zdjęcia, opisy i zapisane w zdjęciach współrzędne GPS są widoczne dla odbiorców linku. Dodawanie przez odbiorców: do 20 zdjęć na godzinę w jednej przeglądarce i 100 zdjęć dziennie na link.</p>
      <footer><span role="status">{{ completed }} / {{ queue.length }} dodanych</span><button :disabled="busy" @click="close">{{ completed ? 'Gotowe' : 'Anuluj' }}</button><button class="primary" :disabled="busy || !pending.length" @click="upload"><Upload :size="16" />{{ busy ? 'Przesyłanie…' : 'Dodaj zdjęcia' }}</button></footer>
    </section>
  </div>
</template>
<style scoped>
.photo-upload-backdrop { position:fixed; inset:0; z-index:1200; background:#15213d66; backdrop-filter:blur(5px); display:grid; place-items:center; padding:20px; }.photo-upload-dialog { width:min(580px,100%); max-height:92dvh; overflow:auto; box-sizing:border-box; background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:18px; padding:24px; }header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }h2 { display:flex; gap:10px; align-items:center; font-size:20px; margin:0 0 12px; }header p { color:var(--muted); font-size:12px; line-height:1.6; margin:0 0 20px; }button { display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:10px 12px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--secondary); font:inherit; font-size:12px; cursor:pointer; }button:disabled { opacity:.5; cursor:default; }button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }.primary { background:var(--accent); color:white; border-color:var(--accent); }.photo-dropzone { width:100%; display:flex; flex-direction:column; padding:25px 16px; border-style:dashed; border-color:var(--accent); background:var(--accent-soft); gap:10px; }.photo-dropzone svg { color:var(--accent); }.photo-dropzone span { font-size:11px; color:var(--muted); }.photo-dropzone.dragging { outline:2px solid var(--accent); }.photo-upload-queue { padding:0; margin:16px 0; list-style:none; max-height:280px; overflow:auto; }.photo-upload-queue li { display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid var(--border); }.photo-upload-queue li>div { flex:1; min-width:0; }.photo-upload-queue strong { display:block; overflow-wrap:anywhere; font-size:12px; }.photo-upload-queue small { display:block; font-size:11px; margin-top:4px; color:var(--muted); }.photo-upload-queue li>svg { flex-shrink:0; }.photo-upload-note { color:var(--muted); font-size:10px; line-height:1.7; }.photo-upload-dialog .upload-error { color:var(--theme-danger,#b92e48); }.upload-success { color:#30976a; }footer { display:flex; align-items:center; gap:8px; margin-top:20px; flex-wrap:wrap; }footer>span { flex:1; color:var(--muted); font-size:11px; }@media(max-width:550px) { .photo-upload-dialog { padding:18px; }footer>span { flex-basis:100%; } }
</style>
