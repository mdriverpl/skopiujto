<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Info, X, MapPin, RotateCcw } from 'lucide-vue-next'
const props = defineProps({ photo: Object, load: Function })
const emit = defineEmits(['close', 'map', 'loaded'])
const data = ref(null), loading = ref(false), error = ref('')
let alive = true, request = 0
const size = bytes => bytes == null ? null : bytes >= 1048576 ? `${(bytes / 1048576).toFixed(2)} MB` : `${Math.ceil(bytes / 1024)} KB`
const rows = computed(() => [
  ['Nazwa pliku', props.photo.filename], ['Rozmiar pliku', size(props.photo.file_size)],
  ['Wymiary', data.value?.width && data.value?.height ? `${data.value.width} × ${data.value.height} px` : null],
  ['Format', data.value?.format], ['Tryb koloru', data.value?.mode]
].filter(([, value]) => value != null && value !== ''))
const coordinates = computed(() => {
  const point = data.value?.location
  return point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude) && Math.abs(point.latitude) <= 90 && Math.abs(point.longitude) <= 180
    ? `${point.latitude.toFixed(6)}, ${point.longitude.toFixed(6)}` : null
})
async function read() {
  if (!props.load) return
  const current = ++request
  loading.value = true; error.value = ''; data.value = null
  try {
    const result = await props.load(props.photo)
    if (alive && current === request) { data.value = result; emit('loaded', { id: props.photo.id, version: props.photo.version, location: result?.location }) }
  }
  catch (err) { if (alive && current === request) error.value = err.message }
  finally { if (alive && current === request) loading.value = false }
}
onMounted(read)
onBeforeUnmount(() => { alive = false; request++ })
</script>
<template>
  <aside class="photo-metadata" aria-label="Metadane zdjęcia">
    <header><strong><Info :size="17" />Metadane zdjęcia</strong><button aria-label="Ukryj metadane zdjęcia" @click="emit('close')"><X :size="18" /></button></header>
    <div class="metadata-scroll"><h3>Plik</h3><dl><template v-for="[name, value] in rows" :key="name"><dt>{{ name }}</dt><dd>{{ value }}</dd></template></dl>
      <p v-if="loading" class="metadata-muted" role="status">Wczytywanie metadanych…</p>
      <div v-else-if="error" class="metadata-error" role="alert"><p>{{ error }}</p><button @click="read"><RotateCcw :size="14" />Spróbuj ponownie</button></div>
      <template v-else><h3>Dane wykonania</h3><dl v-if="data?.tags?.length"><template v-for="(tag, index) in data.tags" :key="index"><dt>{{ tag.name }}</dt><dd>{{ tag.value }}</dd></template></dl><p v-else class="metadata-muted">To zdjęcie nie zawiera danych EXIF o wykonaniu.</p>
        <section v-if="coordinates" class="metadata-location"><h3><MapPin :size="15" />Lokalizacja GPS</h3><p>{{ coordinates }}</p><button @click="emit('map')"><MapPin :size="15" />Pokaż mapę</button></section>
      </template>
    </div>
  </aside>
</template>
<style scoped>
.photo-metadata { display:flex; flex-direction:column; flex:0 0 330px; width:330px; min-height:0; background:#171b25; border-left:1px solid #ffffff18; color:#e5eaf6; font-size:12px; }header { display:flex; align-items:center; justify-content:space-between; padding:10px 14px; border-bottom:1px solid #ffffff14; flex-shrink:0; }header strong { display:flex; align-items:center; gap:8px; font-weight:500; }.photo-metadata button { display:inline-flex; align-items:center; justify-content:center; gap:7px; border:1px solid transparent; border-radius:7px; padding:8px; background:transparent; color:#e5eaf6; font:inherit; font-size:11px; cursor:pointer; }.photo-metadata button:hover { background:#ffffff13; }.photo-metadata button:focus-visible { outline:2px solid #b49bff; outline-offset:2px; }.metadata-scroll { overflow:auto; flex:1; min-height:0; padding:16px; scrollbar-width:thin; }h3 { font-size:11px; font-weight:600; color:#d3d9e7; margin:0 0 14px; }h3:not(:first-child) { margin-top:26px; }dl { margin:0; }dt { color:#8f9bb2; font-size:10px; margin:15px 0 5px; }dd { margin:0; line-height:1.6; white-space:pre-wrap; overflow-wrap:anywhere; font-size:12px; }.metadata-muted { color:#a4adbf; font-size:11px; line-height:1.7; }.metadata-error { color:#ffb4be; line-height:1.7; }.metadata-error button,.metadata-location button { border-color:#ffffff22; }.metadata-location { margin-top:26px; border-top:1px solid #ffffff18; padding-top:18px; }.metadata-location h3 { display:flex; align-items:center; gap:7px; }.metadata-location p { font-size:11px; font-variant-numeric:tabular-nums; }
@media(max-width:800px) { .photo-metadata { width:100%; flex:1 1 45%; min-height:170px; max-height:45dvh; border-left:0; border-top:1px solid #ffffff18; }.metadata-scroll { padding:10px 14px; }header { padding:4px 14px; }dl { display:grid; grid-template-columns:minmax(85px,1fr) minmax(0,1.6fr); gap:9px 12px; align-items:start; }dt { margin:0; line-height:1.7; }dd { font-size:11px; } }
</style>
