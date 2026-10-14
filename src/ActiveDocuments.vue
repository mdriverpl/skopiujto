<script setup>
import { computed, ref } from 'vue'
import { ClipboardList, FileText, Folder, Search, Download, Mail, Pencil, Image, RefreshCw, CheckCircle2, ChevronRight } from 'lucide-vue-next'

const props = defineProps({ documents: Array, folders: Array, busy: Boolean })
const emit = defineEmits(['back', 'refresh', 'open-document', 'open-image', 'open-email', 'change-status', 'open-folder'])
const search = ref(''), filter = ref('all')
const filters = [{ kind: 'all', label: 'Wszystkie' }, { kind: 'signature', label: 'Do podpisania' }, { kind: 'modification', label: 'Do modyfikacji' }, { kind: 'approval', label: 'Akceptacje' }, { kind: 'in_progress', label: 'W toku' }, { kind: 'deadline', label: 'Terminy' }]
const filtered = computed(() => props.documents.filter(doc =>
  (filter.value === 'all' || doc.active_actions.some(action => action.kind === filter.value)) &&
  `${doc.title} ${doc.filename || ''}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
const folderName = doc => props.folders.find(folder => folder.id === doc.folder_id)?.name || 'Mój dysk'
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium' }).format(new Date(value))
const isImage = doc => /\.(jpg|jpeg|png|gif|webp|svg|heic|bmp|avif|ico|tiff?)$/i.test(doc.filename || '')
function open(doc) { emit(isImage(doc) ? 'open-image' : 'open-document', doc) }
</script>

<template>
  <section class="active-documents">
    <nav class="breadcrumbs" aria-label="Ścieżka aktywnych dokumentów"><button :disabled="busy" @click="emit('back')">Mój dysk</button><ChevronRight :size="15" /><span aria-current="page">Aktywne dokumenty</span></nav>
    <header class="active-heading"><Teleport to="#workspace-title"><div><h1>Aktywne dokumenty <span>{{ documents.length }}</span></h1><p>Dokumenty wymagające działania ze wszystkich dostępnych folderów.</p></div></Teleport><button class="icon-button" :disabled="busy" aria-label="Odśwież aktywne dokumenty" title="Odśwież" @click="emit('refresh')"><RefreshCw :size="18" /></button></header>
    <div class="active-toolbar"><Teleport to="#workspace-search"><div class="search"><Search :size="18" /><input v-model="search" aria-label="Szukaj aktywnego dokumentu" placeholder="Szukaj dokumentu…" /></div></Teleport><div class="active-filters" role="group" aria-label="Rodzaj działania"><button v-for="item in filters" :key="item.kind" :aria-pressed="filter === item.kind" @click="filter = item.kind">{{ item.label }}</button></div></div>
    <div class="panel active-list">
      <article v-for="doc in filtered" :key="doc.id" class="active-row">
        <button class="active-open" :disabled="busy" @click="open(doc)"><span class="active-file-icon"><Image v-if="isImage(doc)" :size="21" /><FileText v-else :size="21" /></span><span><strong>{{ doc.title }}</strong><small>{{ doc.filename || doc.category }} · {{ date(doc.updated_at) }}</small></span></button>
        <div class="active-reasons"><span v-for="action in doc.active_actions" :key="action.kind" class="action-badge" :class="action.kind">{{ action.label }}<span v-if="action.count"> · {{ action.count }}</span></span><button class="folder-location" :disabled="busy" @click="emit('open-folder', doc.folder_id)"><Folder :size="12" /> {{ folderName(doc) }}</button></div>
        <div class="active-row-actions"><button v-if="doc.permissions?.workflow" class="status-action" :disabled="busy" @click="emit('change-status', doc)">Zmień status</button><button v-if="doc.approvals" class="icon-button" :disabled="busy" title="Wysyłka i akceptacje" :aria-label="`Akceptacje: ${doc.title}`" @click="emit('open-email', doc)"><Mail :size="17" /></button><a v-if="doc.filename" class="download-button" :href="`/api/documents/${doc.id}/file`" :aria-label="`Pobierz ${doc.filename}`" title="Pobierz"><Download :size="18" /></a><button class="icon-button" :disabled="busy" :aria-label="`Otwórz ${doc.title}`" :title="doc.permissions?.edit ? 'Edytuj dokument' : 'Otwórz dokument'" @click="open(doc)"><Pencil v-if="doc.permissions?.edit" :size="17" /><ChevronRight v-else :size="18" /></button></div>
      </article>
      <div v-if="!filtered.length" class="active-empty"><CheckCircle2 v-if="!documents.length" :size="34" /><ClipboardList v-else :size="34" /><h2>{{ documents.length ? 'Brak pasujących dokumentów' : 'Wszystko na bieżąco' }}</h2><p>{{ documents.length ? 'Zmień wyszukiwanie lub filtr działania.' : 'Nie masz dokumentów wymagających działania. Status możesz zmienić przy pliku na dysku.' }}</p></div>
    </div>
  </section>
</template>

<style scoped>
.active-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
h1 { font-size: 24px; margin: 0; }
h1 span { display: inline-block; vertical-align: middle; font-size: 12px; background: var(--accent-soft); color: var(--accent); border-radius: 7px; padding: 5px 8px; margin-left: 8px; letter-spacing: 0; }
.active-heading p { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
.active-toolbar { display: flex; flex-direction: column; gap: 16px; margin-bottom: 20px; }
.search { max-width: 100%; }
.active-filters { display: flex; flex-wrap: wrap; gap: 7px; }
.active-filters button { padding: 7px 11px; font-size: 12px; border-color: transparent; background: transparent; color: var(--muted); }
.active-filters button[aria-pressed='true'] { background: var(--accent-soft); color: var(--accent); }
.active-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(160px, .65fr) auto; align-items: center; gap: 20px; padding: 20px; border-bottom: 1px solid var(--border); }
.active-row:last-child { border-bottom: none; }
.active-open { display: flex; justify-content: flex-start; text-align: left; background: transparent; padding: 0; border: none; min-width: 0; gap: 12px; }
.active-open > span:last-child { min-width: 0; overflow-wrap: anywhere; }
.active-open strong { font-size: 13px; font-weight: 500; }
.active-open small { display: block; margin-top: 6px; font-size: 11px; color: var(--muted); }
.active-file-icon { display: flex; align-items: center; padding: 10px; background: var(--accent-soft); color: var(--accent); border-radius: 10px; flex-shrink: 0; }
.active-reasons { display: flex; flex-wrap: wrap; gap: 6px; }
.action-badge { border-radius: 6px; padding: 5px 7px; color: var(--accent); background: var(--accent-soft); font-size: 10px; }
.action-badge.signature, .action-badge.approval { color: var(--warning); background: var(--warning-soft); }
.action-badge.deadline { color: var(--theme-danger, #b27070); background: var(--danger-soft); }
.folder-location { flex-basis: 100%; border: none; background: transparent; color: var(--muted); font-size: 10px; justify-content: flex-start; padding: 3px 0 0; text-align: left; }
.active-row-actions { display: flex; align-items: center; gap: 3px; }
.status-action { padding: 7px 10px; font-size: 11px; color: var(--secondary); border-color: var(--border); margin-right: 3px; white-space: nowrap; }
.active-empty { text-align: center; padding: 48px 20px; color: var(--accent); }
.active-empty h2 { color: var(--secondary); font-size: 15px; margin: 14px 0 8px; }
.active-empty p { color: var(--muted); font-size: 12px; line-height: 1.7; margin: 0; }
@media (max-width: 760px) { .active-row { grid-template-columns: minmax(0, 1fr) auto; gap: 14px; } .active-reasons { grid-column: 1 / -1; } .active-row-actions { grid-column: 2; grid-row: 1; } }
@media (max-width: 480px) { .active-row { grid-template-columns: minmax(0, 1fr); padding: 16px; } .active-row-actions { grid-column: 1; grid-row: 3; justify-content: flex-end; } .active-heading h1 { font-size: 21px; } }
</style>
