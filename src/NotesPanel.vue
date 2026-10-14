<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Plus, Search, RefreshCw, StickyNote, Trash2, X, Save } from 'lucide-vue-next'
const props = defineProps({ api: Function, initialDraft: Object })
const emit = defineEmits(['draft-consumed', 'ai'])
const notes = ref([]), search = ref(''), editor = ref(null), busy = ref(false), error = ref('')
const filtered = computed(() => notes.value.filter(note => `${note.title} ${note.content}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action() } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function load() { notes.value = await props.api('/notes') }
function edit(note = { title: '', content: '' }) { error.value = ''; editor.value = { ...note } }
function consumeDraft(draft) {
  if (!draft) return
  edit({ title: draft.title || '', content: draft.content || '' })
  emit('draft-consumed')
}
watch(() => props.initialDraft, consumeDraft, { immediate: true })
async function save() {
  if (!editor.value?.title.trim()) return
  await run(async () => {
    const note = editor.value
    const saved = await props.api(note.id ? `/notes/${note.id}` : '/notes', note.id ? 'PATCH' : 'POST', {
      title: note.title.trim(), content: note.content, ...(note.id ? { version: note.version } : {})
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
onMounted(() => run(load))
</script>
<template>
  <section class="notes-page">
    <header><Teleport to="#workspace-title"><div><h1>Notatki <small>({{ notes.length }})</small></h1><p>Twoje osobiste pomysły, ustalenia i ważne informacje.</p></div></Teleport><div class="actions"><button class="icon-button" :disabled="busy" aria-label="Odśwież notatki" @click="run(load)"><RefreshCw :size="18" /></button><button :disabled="busy" @click="emit('ai')">Dodaj przez AI</button><button class="primary" :disabled="busy" @click="edit()"><Plus :size="17" /> Dodaj notatkę</button></div></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <form v-if="editor" class="panel note-editor" @submit.prevent="save">
      <div class="editor-heading"><h2>{{ editor.id ? 'Edytuj notatkę' : 'Nowa notatka' }}</h2><button type="button" class="icon-button" :disabled="busy" aria-label="Zamknij edytor notatki" @click="editor = null"><X :size="18" /></button></div>
      <label>Tytuł<input v-model="editor.title" maxlength="200" required :disabled="busy" /></label>
      <label>Treść<textarea v-model="editor.content" rows="10" maxlength="20000" :disabled="busy" /></label>
      <div class="actions"><button type="button" :disabled="busy" @click="editor = null">Anuluj</button><button class="primary" :disabled="busy || !editor.title.trim()"><Save :size="17" /> {{ busy ? 'Zapisywanie…' : 'Zapisz notatkę' }}</button></div>
    </form>
    <Teleport to="#workspace-search"><div class="search"><Search :size="18" /><input v-model="search" aria-label="Szukaj notatek" placeholder="Szukaj w tytułach i treści…" /></div></Teleport>
    <p v-if="busy && !notes.length" role="status">Wczytywanie…</p>
    <div v-else class="notes-grid"><article v-for="note in filtered" :key="note.id" class="panel note-card"><button class="note-open" :disabled="busy" @click="edit(note)"><StickyNote :size="20" /><h2>{{ note.title }}</h2><p>{{ note.content || 'Brak treści' }}</p></button><footer><small>{{ date(note.updated_at) }}</small><button class="icon-button" :disabled="busy" :aria-label="`Usuń notatkę: ${note.title}`" @click="remove(note)"><Trash2 :size="16" /></button></footer></article></div>
    <p v-if="!busy && !filtered.length" class="empty">{{ notes.length ? 'Brak pasujących notatek. Zmień wyszukiwanie.' : 'Nie masz jeszcze notatek. Dodaj pierwszą samodzielnie lub z pomocą Edzia.' }}</p>
  </section>
</template>
<style scoped>
header,.editor-heading,.actions,footer { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
header { margin-bottom:24px; } h1 { font-size:24px; margin:0; } h1 small { font-size:14px; color:var(--muted); } header p,.empty { color:var(--muted); }
.search { margin:20px 0; max-width:100%; } .notes-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr)); gap:16px; }
.note-card { padding:20px; min-width:0; } .note-open { display:block; width:100%; padding:0; border:none; background:transparent; text-align:left; overflow-wrap:anywhere; } .note-open svg { color:var(--accent); } h2 { font-size:16px; } .note-open p { white-space:pre-wrap; color:var(--muted); display:-webkit-box; -webkit-line-clamp:5; -webkit-box-orient:vertical; overflow:hidden; line-height:1.6; } footer small { color:var(--muted); font-size:11px; }
.note-editor { padding:24px; } label { display:flex; flex-direction:column; gap:8px; margin-bottom:18px; } .note-editor .actions { justify-content:flex-end; } textarea { resize:vertical; }
</style>
