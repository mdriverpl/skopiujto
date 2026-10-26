<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { Folder, FileText, Download, ChevronRight, ArrowLeft, Link, Images, LayoutGrid, AlertCircle } from 'lucide-vue-next'
import RichTextEditor from './RichTextEditor.vue'
import PhotoGallery from './PhotoGallery.vue'
const props = defineProps({ api: Function, token: String })
const resource = ref(null), detail = ref(null), loading = ref(true), error = ref(''), failedImages = ref({})
let request = 0
const base = computed(() => `/public-shares/${encodeURIComponent(props.token)}`)
const files = computed(() => resource.value?.files || (resource.value?.document ? [resource.value.document] : []))
const gallery = ref(null)
const photos = computed(() => files.value.filter(file => file.image).map(file => ({ ...file, src: url(file, 'preview'), download: url(file, 'file') })))
const otherFiles = computed(() => resource.value?.view_mode === 'gallery' ? files.value.filter(file => !file.image) : files.value)
const url = (file, action) => `/api${base.value}/documents/${encodeURIComponent(file.id)}/${action}`
const size = bytes => bytes == null ? 'Dokument' : bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
const date = stamp => new Date(stamp * 1000).toLocaleDateString('pl-PL')
async function load(folderId = null) {
  const current = ++request
  loading.value = true; error.value = ''; detail.value = null
  try {
    const result = await props.api(base.value + (folderId ? `?folder_id=${encodeURIComponent(folderId)}` : ''))
    if (current !== request) return
    resource.value = result
    loading.value = false
    await nextTick()
    if (result.kind === 'document' && result.view_mode === 'preview') await openDocument(result.document)
  } catch (err) { if (current === request) error.value = err.message }
  finally { if (current === request) loading.value = false }
}
async function openDocument(file, trigger = null) {
  if (file.image) { await gallery.value?.open(file.id, trigger); return }
  const current = request
  loading.value = true; error.value = ''
  try { const result = await props.api(`${base.value}/documents/${encodeURIComponent(file.id)}`); if (current === request) detail.value = result }
  catch (err) { if (current === request) error.value = err.message }
  finally { if (current === request) loading.value = false }
}
onMounted(() => load())
</script>
<template>
  <section class="public-share" aria-label="Udostępniony zasób">
    <header class="public-share-heading"><div><span class="public-eyebrow"><Link :size="15" />Udostępnione przez link</span><h1>{{ resource?.title || 'Udostępniony zasób' }}</h1><p v-if="resource">Dostęp do {{ date(resource.expires) }} · Tylko do odczytu</p></div><a v-if="resource?.kind === 'folder' && !error" class="public-download" :href="`/api${base}/archive`"><Download :size="17" />Pobierz katalog ZIP</a></header>
    <div v-if="error" class="public-error" role="alert"><AlertCircle :size="22" /><div><strong>Nie można otworzyć udostępnienia</strong><p>{{ error }}</p><button @click="load(resource?.folder_id)">Spróbuj ponownie</button></div></div>
    <p v-if="loading" class="public-loading" role="status">Wczytywanie…</p>
    <template v-if="resource && !error && !loading">
      <nav v-if="resource.kind === 'folder' && !detail" class="public-breadcrumbs" aria-label="Ścieżka udostępnionego katalogu"><template v-for="(folder, index) in resource.breadcrumbs" :key="folder.id"><ChevronRight v-if="index" :size="15" /><button :aria-current="folder.id === resource.folder_id ? 'page' : undefined" @click="load(folder.id)">{{ folder.name }}</button></template></nav>
      <div v-if="!detail && resource.folders?.length" class="public-folder-grid"><button v-for="folder in resource.folders || []" :key="folder.id" class="public-folder" @click="load(folder.id)"><Folder :size="30" /><span><strong>{{ folder.name }}</strong><small>Katalog</small></span><ChevronRight :size="18" /></button></div>
      <PhotoGallery ref="gallery" :images="photos" :show-grid="resource.view_mode === 'gallery' && !detail" />
      <section v-if="detail" class="public-detail" aria-label="Podgląd pliku"><div class="public-detail-toolbar"><button v-if="resource.view_mode !== 'preview' || resource.kind === 'folder'" @click="detail = null"><ArrowLeft :size="16" />Wróć do katalogu</button><a class="public-download" :href="url(detail, 'file')"><Download :size="16" />{{ detail.editor ? 'Pobierz PDF' : 'Pobierz plik' }}</a></div><h2>{{ detail.title }}</h2>
        <img v-if="detail.image" class="public-image" :src="url(detail, 'preview')" :alt="detail.title" />
        <iframe v-else-if="detail.pdf" class="public-pdf" :src="url(detail, 'preview')" :title="`Podgląd PDF: ${detail.title}`" sandbox></iframe>
        <RichTextEditor v-if="detail.editor || detail.content" :model-value="detail.rich_content" :plain-text="detail.content" :editable="false" />
        <div v-if="!detail.image && !detail.pdf && !detail.editor && !detail.content" class="public-file-fallback"><FileText :size="50" /><p>{{ detail.filename }}</p><p>Pobierz plik, aby go otworzyć.</p></div>
      </section>
      <div v-else class="public-items" :class="resource.view_mode">
        <article v-for="file in otherFiles" :key="file.id" class="public-file"><button class="public-file-open" @click="openDocument(file, $event.currentTarget)"><img v-if="resource.view_mode === 'gallery' && file.image && !failedImages[file.id]" :src="url(file, 'preview')" :alt="file.title" loading="lazy" @error="failedImages[file.id] = true" /><span v-else class="public-file-icon"><Images v-if="file.image" :size="resource.view_mode === 'catalog' ? 24 : 42" /><FileText v-else :size="resource.view_mode === 'catalog' ? 24 : 42" /></span><span class="public-file-name"><strong>{{ file.title }}</strong><small>{{ file.filename || 'Dokument PDF' }} · {{ size(file.file_size) }}</small></span></button><a class="public-item-download" :href="url(file, 'file')" :aria-label="`Pobierz: ${file.filename || file.title}`"><Download :size="18" /></a></article>
      </div>
      <div v-if="!detail && !files.length && !resource.folders?.length" class="public-empty"><Folder :size="40" /><h2>Ten katalog jest pusty</h2><p>Nie ma w nim dostępnych plików.</p></div>
    </template>
  </section>
</template>
<style scoped>
.public-share { width:min(1180px,100%); margin:0 auto; color:var(--text); }.public-share-heading { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:14px 0 28px; }.public-eyebrow { display:flex; gap:7px; align-items:center; color:var(--accent); font-size:11px; }.public-share-heading h1 { margin:12px 0 9px; font-size:30px; overflow-wrap:anywhere; }.public-share-heading p { color:var(--muted); font-size:11px; margin:0; }button,a { display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:10px 12px; border:1px solid var(--border); border-radius:9px; background:var(--surface); color:var(--secondary); font-size:12px; text-decoration:none; cursor:pointer; }.public-download { color:var(--accent); }.public-breadcrumbs { display:flex; flex-wrap:wrap; align-items:center; gap:6px; margin-bottom:20px; }.public-breadcrumbs button { border:0; background:transparent; padding:7px; }.public-breadcrumbs [aria-current] { color:var(--accent); font-weight:600; }.public-folder-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(min(240px,100%),1fr)); gap:12px; margin-bottom:22px; }.public-folder-grid .public-folder { min-width:0; text-align:left; background:var(--surface); border:1px solid var(--border); border-radius:12px; }
.public-items { display:grid; gap:12px; }.public-items.catalog { grid-template-columns:minmax(0,1fr); }.public-folder { justify-content:flex-start; padding:18px; text-align:left; }.public-folder>svg:first-child { color:#ac8336; }.public-folder>span { flex:1; }.public-folder small,.public-file small { display:block; color:var(--muted); font-size:11px; margin-top:6px; overflow-wrap:anywhere; }.public-folder strong,.public-file strong { font-size:13px; overflow-wrap:anywhere; }.public-file { display:flex; align-items:center; gap:8px; padding:8px; border:1px solid var(--border); border-radius:12px; background:var(--surface); min-width:0; }.public-file-open { flex:1; min-width:0; border:0; justify-content:flex-start; text-align:left; }.public-file-icon { display:grid; place-items:center; flex-shrink:0; color:var(--accent); padding:8px; background:var(--accent-soft); border-radius:9px; }.public-file-name { min-width:0; flex:1; }.public-item-download { flex-shrink:0; border:0; color:var(--accent); }.public-items.gallery,.public-items.tiles { grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); align-items:start; }.gallery .public-file,.tiles .public-file { display:flex; flex-direction:column; align-items:stretch; padding:0; overflow:hidden; }.gallery .public-file-open,.tiles .public-file-open { flex-direction:column; align-items:stretch; gap:0; padding:0; }.gallery .public-file-open>img { width:100%; height:220px; object-fit:cover; }.gallery .public-file-icon { height:220px; border-radius:0; padding:0; }.tiles .public-file-icon { height:110px; border-radius:0; padding:0; }.gallery .public-file-name,.tiles .public-file-name { padding:16px; }.gallery .public-item-download,.tiles .public-item-download { border-top:1px solid var(--border); border-radius:0; background:var(--surface-soft); }.gallery .public-folder,.tiles .public-folder { min-height:110px; }.public-detail { padding:24px; background:var(--surface); border:1px solid var(--border); border-radius:16px; }.public-detail-toolbar { display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }.public-detail h2 { font-size:22px; margin:24px 0; overflow-wrap:anywhere; }.public-image { display:block; max-width:100%; max-height:75vh; margin:0 auto 24px; object-fit:contain; }.public-pdf { width:100%; height:75vh; border:1px solid var(--border); border-radius:8px; background:white; }.public-file-fallback,.public-empty { padding:60px 20px; text-align:center; color:var(--muted); }.public-file-fallback p,.public-empty p { font-size:12px; }.public-empty h2 { font-size:18px; }.public-error { display:flex; gap:14px; padding:24px; border:1px solid var(--border); background:var(--surface); border-radius:14px; color:var(--theme-danger,#ba253b); }.public-error p,.public-loading { font-size:12px; }.public-error>svg { flex-shrink:0; }
@media(max-width:600px) { .public-share-heading { flex-direction:column; align-items:flex-start; }.public-share-heading h1 { font-size:24px; }.public-items.gallery,.public-items.tiles { grid-template-columns:minmax(0,1fr); }.public-detail { padding:16px; }.public-file-open { padding:8px; } }
</style>
