<script setup>
import { computed, ref } from 'vue'
import { Paperclip, Upload, HardDrive, X, Archive, Download, Eye, EyeOff, Search } from 'lucide-vue-next'
const props = defineProps({ api: Function, modelValue: Object, disabled: Boolean })
const emit = defineEmits(['update:modelValue', 'download-zip'])
const fileInput = ref(null), picker = ref(false), drive = ref([]), query = ref(''), chosen = ref([])
const loading = ref(false), error = ref(''), showPassword = ref(false)
const items = computed(() => [
  ...props.modelValue.existing.filter(file => !props.modelValue.removed.includes(file.id)).map(file => ({ ...file, source: 'existing' })),
  ...props.modelValue.files.map((file, index) => ({ name: file.name, size: file.size, index, source: 'computer' })),
  ...props.modelValue.drive.map(file => ({ ...file, name: file.filename, size: file.file_size, source: 'drive' }))
])
const results = computed(() => drive.value.filter(file => `${file.filename} ${file.title}`.toLocaleLowerCase('pl').includes(query.value.toLocaleLowerCase('pl'))))
function update(patch) { emit('update:modelValue', { ...props.modelValue, ...patch }) }
function size(bytes) { return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.ceil((bytes || 0) / 1024)} KB` }
function remove(file) {
  if (file.source === 'existing') update({ removed: [...props.modelValue.removed, file.id] })
  if (file.source === 'computer') update({ files: props.modelValue.files.filter((_, index) => index !== file.index) })
  if (file.source === 'drive') update({ drive: props.modelValue.drive.filter(item => item.id !== file.id) })
}
function addComputer(event) {
  const files = [...(event.target.files || [])]
  error.value = ''
  if (items.value.length + files.length > 50 || items.value.reduce((sum, item) => sum + (item.size || 0), 0) + files.reduce((sum, file) => sum + file.size, 0) > 20 * 1048576) {
    error.value = 'Dodaj maksymalnie 50 plików o łącznym rozmiarze do 20 MB.'
  } else update({ files: [...props.modelValue.files, ...files] })
  event.target.value = ''
}
async function openDrive() {
  picker.value = true; loading.value = true; error.value = ''; chosen.value = []; query.value = ''
  try { drive.value = (await props.api('/documents')).filter(file => file.filename && file.permissions?.read !== false) }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}
function addDrive() {
  const added = drive.value.filter(file => chosen.value.includes(file.id) && !props.modelValue.drive.some(item => item.id === file.id))
  if (items.value.length + added.length > 50 || [...items.value, ...added.map(file => ({ size: file.file_size }))].reduce((sum, item) => sum + (item.size || 0), 0) > 20 * 1048576) {
    error.value = 'Dodaj maksymalnie 50 plików o łącznym rozmiarze do 20 MB.'; return
  }
  update({ drive: [...props.modelValue.drive, ...added] }); picker.value = false
}
</script>
<template>
  <section class="compose-attachments" aria-label="Załączniki do wiadomości">
    <header><strong><Paperclip :size="16" />Załączniki <small>{{ items.length }}</small></strong><span>Do 50 plików · 20 MB</span></header>
    <div class="attachment-buttons"><button type="button" :disabled="disabled" @click="fileInput.click()"><Upload :size="15" />Z komputera</button><button type="button" :disabled="disabled" @click="openDrive"><HardDrive :size="15" />Z Dysku</button></div>
    <input ref="fileInput" class="file-input" type="file" multiple :disabled="disabled" aria-label="Dodaj pliki z komputera" @change="addComputer" />
    <ul v-if="items.length" class="attachment-list"><li v-for="(file, index) in items" :key="index"><Paperclip :size="14" /><span>{{ file.name }}<small>{{ size(file.size) }} · {{ file.source === 'computer' ? 'Komputer' : file.source === 'drive' ? 'Dysk' : 'Zapisany' }}</small></span><button type="button" :disabled="disabled" :aria-label="`Usuń załącznik: ${file.name}`" @click="remove(file)"><X :size="15" /></button></li></ul>
    <p v-else class="attachment-empty">Dodaj pliki z komputera lub Dysku portalu.</p>
    <label class="zip-toggle"><input type="checkbox" :checked="modelValue.zip_enabled" :disabled="disabled" @change="update({ zip_enabled: $event.target.checked })" /><Archive :size="16" />Spakuj załączniki do jednego ZIP</label>
    <div v-if="modelValue.zip_enabled" class="zip-options">
      <label>Nazwa archiwum<input :value="modelValue.zip_name" maxlength="200" :disabled="disabled" placeholder="zalaczniki.zip" @input="update({ zip_name: $event.target.value })" /></label>
      <label>Hasło ZIP <small>(opcjonalnie)</small><span class="password-field"><input :value="modelValue.zip_password" :type="showPassword ? 'text' : 'password'" maxlength="200" :disabled="disabled" autocomplete="new-password" placeholder="Bez hasła" @input="update({ zip_password: $event.target.value })" /><button type="button" :disabled="disabled" :aria-label="showPassword ? 'Ukryj hasło ZIP' : 'Pokaż hasło ZIP'" @click="showPassword = !showPassword"><component :is="showPassword ? EyeOff : Eye" :size="16" /></button></span></label>
      <small>Hasło zostanie zapisane przy Twojej wiadomości. Przekaż je odbiorcy osobno.</small>
      <button type="button" class="download-zip" :disabled="disabled || !items.length" @click="emit('download-zip')"><Download :size="15" />Zapisz ZIP na komputerze</button>
    </div>
    <p v-if="error" class="attachment-error" role="alert">{{ error }}</p>
    <section v-if="picker" class="drive-picker" aria-label="Wybierz pliki z Dysku">
      <header><strong><HardDrive :size="16" />Pliki z Dysku</strong><button type="button" aria-label="Zamknij wybór plików" @click="picker = false"><X :size="16" /></button></header>
      <label class="drive-search"><Search :size="16" /><input v-model="query" type="search" aria-label="Szukaj pliku na Dysku" placeholder="Szukaj pliku…" /></label>
      <p v-if="loading" role="status">Wczytywanie plików…</p>
      <div v-else class="drive-files"><label v-for="file in results" :key="file.id"><input v-model="chosen" type="checkbox" :value="file.id" :disabled="modelValue.drive.some(item => item.id === file.id)" /><span>{{ file.filename }}<small>{{ file.title }} · {{ size(file.file_size) }}</small></span></label><p v-if="!results.length">Brak dostępnych plików.</p></div>
      <button type="button" class="primary" :disabled="loading || !chosen.length" @click="addDrive">Dodaj wybrane ({{ chosen.length }})</button>
    </section>
  </section>
</template>
<style scoped>
.compose-attachments { display:grid; gap:12px; padding:16px; border:1px solid var(--border); border-radius:12px; background:var(--surface-soft); font-size:12px; min-width:0; }
header,header strong,.attachment-buttons,.zip-toggle,.password-field,.drive-search { display:flex; align-items:center; gap:8px; }header { justify-content:space-between; }header strong { font-weight:600; }header>span,small,.attachment-empty { color:var(--muted); font-size:11px; }header>span { text-align:right; }
button { display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:8px 10px; font:inherit; border:1px solid var(--border); border-radius:8px; color:var(--secondary); background:var(--surface); }button:disabled { opacity:.5; cursor:default; }.file-input { display:none; }.attachment-buttons { flex-wrap:wrap; }.attachment-empty { margin:0; }.attachment-list { display:grid; gap:6px; margin:0; padding:0; list-style:none; }.attachment-list li { display:flex; align-items:center; gap:8px; min-width:0; padding:8px; background:var(--surface); border-radius:8px; }.attachment-list li>span { flex:1; min-width:0; overflow-wrap:anywhere; }.attachment-list small,.drive-files small { display:block; margin-top:3px; }.attachment-list button { padding:5px; border:0; }.zip-toggle { cursor:pointer; line-height:1.5; }.zip-toggle input,.drive-files input { flex-shrink:0; }.zip-options { display:grid; gap:10px; }.zip-options>label { display:grid; gap:6px; }.zip-options input,.drive-search input { width:100%; box-sizing:border-box; min-width:0; padding:9px 10px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--text); font:inherit; }.password-field input { flex:1; }.password-field button { padding:8px; }.zip-options>small { line-height:1.6; }.download-zip { justify-self:start; }.attachment-error { color:var(--theme-danger,#ba253b); margin:0; }.drive-picker { display:grid; gap:12px; border-top:1px solid var(--border); padding-top:14px; }.drive-search input { flex:1; }.drive-files { max-height:240px; overflow:auto; display:grid; gap:6px; }.drive-files label { display:flex; gap:9px; align-items:center; padding:8px; background:var(--surface); border-radius:7px; overflow-wrap:anywhere; }.drive-picker>.primary { justify-self:end; color:var(--accent); }
.compose-attachments .zip-toggle,.compose-attachments .drive-files label { display:flex; flex-direction:row; align-items:center; justify-content:flex-start; }
.compose-attachments input[type="checkbox"] { width:15px; height:15px; flex:0 0 15px; margin:0; padding:0; }
.compose-attachments .zip-toggle>svg { flex-shrink:0; }
@media(max-width:500px) { .compose-attachments { padding:12px; }header { align-items:flex-start; } }
</style>
