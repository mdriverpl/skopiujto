<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Plus, Search, RefreshCw, StickyNote, Trash2, X, Save, Pencil } from 'lucide-vue-next'
const props = defineProps({ api: Function, initialDraft: Object })
const emit = defineEmits(['draft-consumed', 'ai'])
const notes = ref([]), search = ref(''), editor = ref(null), busy = ref(false), error = ref('')
const noteDialog = ref(null)
watch(editor, value => {
  if (value) noteDialog.value?.showModal()
  else noteDialog.value?.close()
}, { flush: 'post' })
function closeEditor() { if (!busy.value) editor.value = null }
const filtered = computed(() => notes.value.filter(note => `${note.title} ${note.content}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action() } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function load() { notes.value = await props.api('/notes') }
function edit(note = { title: '', content: '' }) {
  if (busy.value) return
  error.value = ''; editor.value = { ...note, content: note.content || note.title || '' }
}
function consumeDraft(draft) {
  if (!draft) return
  edit({ title: draft.title || '', content: draft.content || '' })
  emit('draft-consumed')
}
watch(() => props.initialDraft, consumeDraft, { immediate: true })
async function save() {
  if (!editor.value?.content.trim()) return
  await run(async () => {
    const note = editor.value
    const saved = await props.api(note.id ? `/notes/${note.id}` : '/notes', note.id ? 'PATCH' : 'POST', {
      title: note.title?.trim() || note.content.trim().split(/\r?\n/)[0].slice(0, 200), content: note.content, ...(note.id ? { version: note.version } : {})
    })
    notes.value = [saved, ...notes.value.filter(item => item.id !== saved.id)]
    editor.value = null
  })
}
async function remove(note) {
  if (busy.value || !window.confirm(`Usunąć notatkę „${note.title}”?`)) return
  await run(async () => {
    await props.api(`/notes/${note.id}`, 'DELETE')
    notes.value = notes.value.filter(item => item.id !== note.id)
  })
}
onMounted(() => { if (editor.value) noteDialog.value?.showModal(); run(load) })
</script>
<template>
  <section class="notes-page">
    <header class="page-menu"><Teleport to="#workspace-title"><div><h1>Notatki <small>({{ notes.length }})</small></h1><p>Twoje osobiste pomysły, ustalenia i ważne informacje.</p></div></Teleport><div class="actions"><button class="icon-button" :disabled="busy" aria-label="Odśwież notatki" @click="run(load)"><RefreshCw :size="18" /></button><button :disabled="busy" @click="emit('ai')">Dodaj przez AI</button><button class="primary" :disabled="busy" @click="edit()"><Plus :size="17" /> Dodaj notatkę</button></div></header>
    <p v-if="error && !editor" class="error" role="alert">{{ error }}</p>
    <dialog ref="noteDialog" class="note-dialog" aria-labelledby="note-editor-title" @cancel.prevent="closeEditor" @close="editor = null">
      <form v-if="editor" class="note-editor" @submit.prevent="save">
        <header class="note-dialog-heading"><span class="note-graphic" aria-hidden="true"><StickyNote :size="26" :stroke-width="1.5" /></span><div><small>Twoje notatki</small><h2 id="note-editor-title">{{ editor.id ? 'Edytuj notatkę' : 'Nowa notatka' }}</h2></div><button type="button" class="icon-button" :disabled="busy" aria-label="Zamknij edytor notatki" @click="closeEditor"><X :size="18" /></button></header>
        <div class="note-editor-body"><p v-if="error" class="error" role="alert">{{ error }}</p><label>Treść notatki<textarea v-model="editor.content" autofocus rows="9" maxlength="20000" required :disabled="busy" placeholder="Zapisz pomysł, ustalenia lub ważną informację…" /></label></div>
        <footer class="note-editor-actions"><button type="button" :disabled="busy" @click="closeEditor">Anuluj</button><button type="submit" class="primary" :disabled="busy || !editor.content.trim()"><Save :size="15" /> {{ busy ? 'Zapisywanie…' : 'Zapisz notatkę' }}</button></footer>
      </form>
    </dialog>
    <Teleport to="#workspace-search"><div class="search"><Search :size="18" /><input v-model="search" aria-label="Szukaj notatek" placeholder="Szukaj w notatkach…" /></div></Teleport>
    <p v-if="busy && !notes.length" role="status">Wczytywanie…</p>
    <div v-else class="notes-grid"><article v-for="note in filtered" :key="note.id" class="panel note-card"><button class="note-open" :disabled="busy" :aria-label="`Edytuj notatkę: ${(note.content || note.title).slice(0, 80)}`" @click="edit(note)"><span class="note-card-heading"><span class="note-graphic" aria-hidden="true"><StickyNote :size="23" :stroke-width="1.5" /></span><Pencil :size="14" class="note-edit-icon" aria-hidden="true" /></span><p>{{ note.content || note.title }}</p></button><footer><small>{{ date(note.updated_at) }}</small><button class="icon-button" :disabled="busy" :aria-label="`Usuń notatkę: ${note.title}`" @click="remove(note)"><Trash2 :size="14" /></button></footer></article></div>
    <p v-if="!busy && !filtered.length" class="empty">{{ notes.length ? 'Brak pasujących notatek. Zmień wyszukiwanie.' : 'Nie masz jeszcze notatek. Dodaj pierwszą samodzielnie lub z pomocą Edzia.' }}</p>
  </section>
</template>
<style scoped>
header,.actions,footer { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
.notes-page > header { margin-bottom:20px; } h1 { font-size:24px; margin:0; } h1 small { font-size:14px; color:var(--muted); } header p,.empty { color:var(--muted); }
.search { margin:20px 0; max-width:100%; }
.notes-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(min(100%,200px),1fr)); gap:12px; }
.note-card { padding:14px; min-width:0; display:flex; flex-direction:column; height:176px; border-radius:12px; }
.note-open { display:flex; flex:1; min-height:0; flex-direction:column; justify-content:flex-start; align-items:stretch; gap:10px; width:100%; padding:0; border:none; background:transparent; text-align:left; overflow-wrap:anywhere; }
.note-open:hover { background:transparent; }
.note-card-heading { display:flex; align-items:center; justify-content:space-between; width:100%; }
.note-graphic { display:inline-flex; align-items:center; justify-content:center; padding:9px; color:var(--warning); background:var(--warning-soft); border-radius:11px; flex-shrink:0; }
.note-edit-icon { color:var(--muted); }
.note-open:hover .note-edit-icon { color:var(--accent); }
.note-open p { margin:0; white-space:pre-wrap; color:var(--text); display:-webkit-box; -webkit-line-clamp:3; line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; line-height:1.6; font-size:12px; }
.note-card footer { margin-top:10px; gap:4px; flex-wrap:nowrap; }
.note-card footer small { color:var(--muted); font-size:10px; }
.note-card footer button { padding:6px; color:var(--muted); }
.note-dialog { width:min(540px,calc(100vw - 32px)); max-height:90dvh; padding:0; border:1px solid var(--border); border-radius:16px; color:var(--text); background:var(--surface); box-shadow:0 24px 70px #0002; }
.note-dialog[open] { display:flex; flex-direction:column; }
.note-dialog::backdrop { background:#13213966; backdrop-filter:blur(4px); }
.note-editor { display:flex; flex-direction:column; min-height:0; overflow:hidden; }
.note-dialog-heading { padding:16px 20px; gap:12px; flex-wrap:nowrap; border-bottom:1px solid var(--border); background:linear-gradient(120deg,var(--warning-soft),var(--surface) 80%); }
.note-dialog-heading > div { flex:1; min-width:0; }
.note-dialog-heading small { color:var(--muted); font-size:10px; }
.note-dialog-heading h2 { font-size:17px; font-weight:600; margin:4px 0 0; }
.note-editor-body { padding:20px; overflow:auto; }
.note-editor label { gap:8px; font-size:12px; font-weight:400; }
.note-editor textarea { font-size:13px; line-height:1.7; resize:vertical; min-height:160px; max-height:50dvh; }
.note-editor-actions { justify-content:flex-end; padding:12px 20px; border-top:1px solid var(--border); }
.note-editor-actions button { padding:8px 12px; font-size:12px; }
@media(max-width:480px) { .notes-grid { grid-template-columns:repeat(auto-fill,minmax(min(100%,155px),1fr)); }.note-dialog { width:calc(100vw - 20px); max-height:94dvh; }.note-dialog-heading,.note-editor-body,.note-editor-actions { padding:14px; } }
</style>
