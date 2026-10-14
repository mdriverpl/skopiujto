<script setup>
import { computed, ref, toRaw } from 'vue'
import { FileText, Plus, Search, X, Save, Copy, ArrowUpRight, Pencil, BookOpen, RefreshCw, Trash2, Sparkles, History } from 'lucide-vue-next'
import RichTextEditor from './RichTextEditor.vue'
import AiPrompt from './AiPrompt.vue'

const props = defineProps({ templates: Array, api: Function, canAdd: Boolean })
const emit = defineEmits(['updated', 'created-document', 'history'])
const search = ref(''), category = ref('Wszystkie'), scope = ref('all'), draft = ref(null), mode = ref('preview'), busy = ref(false), error = ref(''), message = ref('')
const deleting = ref(null)
const aiDialog = ref(false), aiBusy = ref(false)
function generatedTemplate(item) { aiDialog.value = false; open(item, 'create') }
const categories = computed(() => [...new Set(props.templates.map(item => item.category))].sort((a, b) => a.localeCompare(b, 'pl')))
const filtered = computed(() => props.templates.filter(item =>
  (category.value === 'Wszystkie' || item.category === category.value) && (scope.value === 'all' || (scope.value === 'mine' ? item.user_id !== null : item.user_id === null)) &&
  `${item.title} ${item.description} ${item.category}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
let initialDraft = ''
const snapshot = () => JSON.stringify({ title: draft.value.title, category: draft.value.category, description: draft.value.description, content: draft.value.content, rich_content: draft.value.rich_content })
const editable = computed(() => mode.value !== 'preview')
function open(item, nextMode = 'preview') {
  draft.value = structuredClone(toRaw(item)); mode.value = nextMode; error.value = ''; message.value = ''
  if (nextMode === 'copy') { draft.value.id = null; draft.value.title += ' — kopia' }
  initialDraft = snapshot()
}
function create() { draft.value = { title: '', category: 'Inne', description: '', content: '', rich_content: null }; mode.value = 'create'; error.value = ''; initialDraft = snapshot() }
function close() {
  if (busy.value) return
  if (editable.value && snapshot() !== initialDraft && !window.confirm('Zamknąć edytor bez zapisywania zmian?')) return
  draft.value = null; error.value = ''
}
async function save() {
  if (busy.value || !editable.value) return
  busy.value = true; error.value = ''
  try {
    const updating = !!draft.value.id
    await props.api(updating ? `/templates/${draft.value.id}` : '/templates', updating ? 'PUT' : 'POST', {
      title: draft.value.title, category: draft.value.category, description: draft.value.description, content: draft.value.content,
      rich_content: draft.value.rich_content, ...(updating ? { version: draft.value.version } : {})
    })
    draft.value = null; message.value = 'Szablon zapisany.'; emit('updated')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function useTemplate(item) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const doc = await props.api('/documents', 'POST', { title: item.title, category: item.category, content: item.content, rich_content: item.rich_content, status: 'Szkic' })
    draft.value = null; emit('created-document', doc)
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function remove() {
  if (busy.value || !deleting.value?.permissions?.delete) return
  busy.value = true; error.value = ''
  try {
    await props.api(`/templates/${deleting.value.id}`, 'DELETE')
    deleting.value = null; message.value = 'Szablon usunięty.'; emit('updated')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
</script>

<template>
  <section class="templates-panel">
    <header class="templates-heading"><Teleport to="#workspace-title"><div><h1>Szablony <span>{{ templates.length }}</span></h1><p>Gotowe wzory i Twoje pomysły na kolejne dokumenty.</p></div></Teleport><div v-if="canAdd" class="heading-actions"><button class="ai-button" :disabled="busy" @click="aiDialog = true"><Sparkles :size="17" /> Utwórz z AI</button><button class="primary" :disabled="busy" @click="create"><Plus :size="17" /> Nowy szablon</button></div></header>
    <p v-if="message" class="success" role="status">{{ message }}</p><p v-if="error && !draft && !deleting" class="error" role="alert">{{ error }}</p>
    <div class="templates-toolbar"><Teleport to="#workspace-search"><div class="search"><Search :size="17" /><input v-model="search" placeholder="Szukaj szablonu…" aria-label="Szukaj szablonu" /></div></Teleport><div class="template-controls"><select v-model="category" aria-label="Kategoria szablonu"><option>Wszystkie</option><option v-for="item in categories" :key="item">{{ item }}</option></select><button class="icon-button" :disabled="busy" title="Odśwież szablony" aria-label="Odśwież szablony" @click="emit('updated')"><RefreshCw :size="17" /></button></div></div>
    <div class="scope-filters" role="group" aria-label="Zestaw szablonów"><button :aria-pressed="scope === 'all'" @click="scope = 'all'">Wszystkie</button><button :aria-pressed="scope === 'mine'" @click="scope = 'mine'">Moje szablony</button><button :aria-pressed="scope === 'ready'" @click="scope = 'ready'">Gotowe wzory</button></div>
    <div class="template-cards">
      <article v-for="item in filtered" :key="item.id" class="template-card">
        <button class="card-preview" :disabled="busy" :aria-label="`Podgląd szablonu ${item.title}`" @click="open(item)"><span class="preview-paper"><span class="preview-paper-title">{{ item.content.split('\n').find(line => line.trim()) || item.title }}</span><span class="preview-paper-text">{{ item.content.slice(0, 350) }}</span><span class="preview-fade"></span></span><span class="preview-open"><ArrowUpRight :size="16" /></span></button>
        <div class="card-body"><div class="card-tags"><span class="category-tag">{{ item.category }}</span><span>{{ item.user_id === null ? 'Gotowy wzór' : 'Mój szablon' }}</span></div><h2>{{ item.title }}</h2><p>{{ item.description || 'Własny wzór dokumentu.' }}</p></div>
        <footer class="card-actions"><button class="text-button" :disabled="busy" title="Historia zmian" @click="emit('history', item)"><History :size="15" /> Historia</button><button class="text-button" :disabled="busy" @click="open(item)"><BookOpen :size="15" /> Podgląd</button><button v-if="item.permissions?.edit" class="text-button" :disabled="busy" @click="open(item, 'edit')"><Pencil :size="14" /> Edytuj</button><button v-else-if="canAdd" class="text-button" :disabled="busy" @click="open(item, 'copy')"><Copy :size="14" /> Utwórz kopię</button><button v-if="item.permissions?.delete" class="text-button remove-template" :disabled="busy" :aria-label="`Usuń szablon ${item.title}`" title="Usuń szablon" @click="deleting = item; error = ''"><Trash2 :size="15" /></button></footer>
      </article>
    </div>
    <div v-if="!filtered.length" class="templates-empty"><FileText :size="34" /><h2>Brak pasujących szablonów</h2><p>Zmień filtry lub utwórz swój pierwszy szablon.</p></div>
    <div v-if="aiDialog" class="modal-backdrop" @keydown.esc="!aiBusy && (aiDialog = false)">
      <section class="panel ai-template-dialog" role="dialog" aria-modal="true" aria-labelledby="ai-template-title">
        <header class="template-editor-heading"><span class="editor-mark"><Sparkles :size="20" /></span><div><h2 id="ai-template-title">Szablon z AI</h2><p>Opisz wzór, który chcesz przygotować.</p></div><button class="icon-button" :disabled="aiBusy" aria-label="Zamknij generator szablonu" @click="aiDialog = false"><X :size="20" /></button></header>
        <div class="ai-template-body"><AiPrompt :api="api" kind="template" @busy="aiBusy = $event" @generated="generatedTemplate" /></div>
      </section>
    </div>
    <div v-if="deleting" class="modal-backdrop" @keydown.esc="!busy && (deleting = null)">
      <section class="panel delete-confirmation" role="alertdialog" aria-modal="true" aria-labelledby="delete-template-title" aria-describedby="delete-template-description">
        <span class="delete-mark"><Trash2 :size="23" /></span>
        <h2 id="delete-template-title">Usunąć szablon?</h2>
        <p id="delete-template-description">„{{ deleting.title }}” zostanie usunięty. Dokumenty utworzone z tego szablonu pozostaną na dysku.</p>
        <p v-if="deleting.user_id === null" class="delete-note">To gotowy wzór dostępny dla wszystkich użytkowników.</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="delete-actions"><button :disabled="busy" autofocus @click="deleting = null; error = ''">Anuluj</button><button class="delete-submit" :disabled="busy" @click="remove"><Trash2 :size="16" /> {{ busy ? 'Usuwanie…' : 'Usuń szablon' }}</button></div>
      </section>
    </div>
    <div v-if="draft" class="modal-backdrop">
      <section class="panel template-editor" role="dialog" aria-modal="true" aria-labelledby="template-editor-title">
        <header class="template-editor-heading"><span class="editor-mark"><FileText :size="20" /></span><div><h2 id="template-editor-title">{{ mode === 'preview' ? draft.title : mode === 'edit' ? 'Edytuj szablon' : mode === 'copy' ? 'Utwórz kopię szablonu' : 'Nowy szablon' }}</h2><p>{{ mode === 'copy' ? 'Zapiszesz własną kopię w swoich szablonach.' : editable ? 'Nadaj treści własny styl.' : draft.category }}</p></div><button v-if="draft.id" class="icon-button" :disabled="busy" title="Historia zmian" aria-label="Historia szablonu" @click="emit('history', draft)"><History :size="18" /></button><button class="icon-button" :disabled="busy" aria-label="Zamknij szablon" @click="close"><X :size="20" /></button></header>
        <form id="template-form" class="template-editor-body" @submit.prevent="save">
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <div v-if="editable" class="template-fields"><label>Nazwa szablonu<input v-model="draft.title" :disabled="busy" required maxlength="200" placeholder="np. Umowa z klientem" /></label><label>Kategoria<input v-model="draft.category" :disabled="busy" maxlength="60" list="template-categories" /><datalist id="template-categories"><option v-for="item in categories" :key="item">{{ item }}</option></datalist></label><label class="description-field">Krótki opis<input v-model="draft.description" :disabled="busy" maxlength="500" placeholder="Do czego służy ten szablon?" /></label></div>
          <p v-else-if="draft.description" class="preview-description">{{ draft.description }}</p>
          <RichTextEditor :key="`${draft.id || 'new'}-${mode}`" v-model="draft.rich_content" v-model:plain-text="draft.content" :editable="editable && !busy" label="Treść szablonu" />
        </form>
        <footer class="template-editor-footer"><span>{{ editable ? 'Formatowanie zostanie zapisane w szablonie.' : 'Wzór gotowy do dostosowania.' }}</span><div><button :disabled="busy" class="text-button" @click="close">{{ editable ? 'Anuluj' : 'Zamknij' }}</button><button v-if="editable" class="primary" type="submit" form="template-form" :disabled="busy || !draft.title.trim()"><Save :size="16" /> {{ busy ? 'Zapisywanie…' : mode === 'copy' || mode === 'create' ? 'Zapisz nowy szablon' : 'Zapisz zmiany' }}</button><template v-else><button v-if="draft.permissions?.edit || canAdd" :disabled="busy" @click="open(draft, draft.permissions?.edit ? 'edit' : 'copy')"><Pencil :size="16" /> {{ draft.permissions?.edit ? 'Edytuj' : 'Utwórz kopię' }}</button><button v-if="canAdd" class="primary" :disabled="busy" @click="useTemplate(draft)"><Plus :size="16" /> Utwórz dokument</button></template></div></footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.templates-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
h1 { font-size: 25px; margin: 0; }
h1 span { display: inline-block; font-size: 12px; background: var(--accent-soft); color: var(--accent); border-radius: 6px; padding: 4px 7px; margin-left: 8px; vertical-align: middle; letter-spacing: 0; }
.templates-heading p { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
.templates-heading .primary { font-size: 12px; }
.heading-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.heading-actions button { font-size: 12px; }
.heading-actions .ai-button { color: var(--accent); border-color: var(--theme-accent-soft, #e2dafa); background: var(--accent-soft); }
.ai-template-dialog { width: 640px; max-width: 100%; max-height: 92vh; overflow-y: auto; border-radius: 18px; }
.ai-template-body { padding: 0 24px 24px; }
.templates-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.search { max-width: 100%; }
.template-controls { display: flex; align-items: center; gap: 6px; }
.template-controls select { font-size: 12px; }
.scope-filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 22px; }
.scope-filters button { border: none; background: transparent; color: var(--muted); font-size: 12px; padding: 7px 10px; }
.scope-filters button[aria-pressed='true'] { color: var(--accent); background: var(--accent-soft); }
.template-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px; }
.template-card { border: 1px solid var(--border); border-radius: 14px; background: var(--surface); overflow: hidden; display: flex; flex-direction: column; transition: box-shadow .15s, border-color .15s; }
.template-card:hover { border-color: var(--theme-accent-soft, #d9d1f5); box-shadow: 0 6px 22px #6654d909; }
.card-preview { height: 165px; width: 100%; border: none; border-bottom: 1px solid var(--border); border-radius: 0; padding: 22px 28px 0; background: var(--surface-soft); position: relative; overflow: hidden; }
.preview-paper { display: block; height: 180px; padding: 18px; border: 1px solid var(--border); border-radius: 4px 4px 0 0; background: var(--surface); box-shadow: 0 2px 10px #25283d06; overflow: hidden; text-align: left; min-width: 0; width: 100%; }
.preview-paper-title { display: block; font-size: 8px; font-weight: 600; color: var(--theme-muted, #74798d); max-height: 25px; overflow: hidden; margin-bottom: 10px; }
.preview-paper-text { display: block; white-space: pre-wrap; color: var(--theme-muted, #b0b4c2); font-size: 6px; line-height: 1.8; overflow-wrap: anywhere; }
.preview-fade { position: absolute; bottom: 0; left: 0; right: 0; height: 35px; background: linear-gradient(transparent, var(--surface-soft)); }
.preview-open { position: absolute; right: 12px; top: 12px; display: flex; background: var(--surface); color: var(--muted); padding: 5px; border-radius: 6px; }
.card-body { padding: 18px; flex: 1; }
.card-tags { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: var(--muted); font-size: 10px; }
.category-tag { background: var(--accent-soft); color: var(--accent); border-radius: 5px; padding: 4px 7px; }
.card-body h2 { font-size: 14px; font-weight: 600; margin: 12px 0 8px; overflow-wrap: anywhere; }
.card-body p { font-size: 11px; color: var(--muted); line-height: 1.7; margin: 0; overflow-wrap: anywhere; }
.card-actions { display: flex; justify-content: space-between; padding: 12px 18px; border-top: 1px solid var(--border); }
.text-button { font-size: 11px; border: none; padding: 4px 0; background: transparent; color: var(--muted); }
.text-button:hover { color: var(--accent); background: transparent; }
.remove-template { color: var(--theme-danger, #b77878); padding: 4px; }
.remove-template:hover { color: var(--theme-danger, #bc4646); }
.delete-confirmation { width: 430px; max-width: 100%; padding: 28px; border-radius: 16px; }
.delete-mark { display: inline-flex; padding: 12px; background: var(--theme-danger-soft, #fff0f0); color: var(--theme-danger, #bc6262); border-radius: 12px; }
.delete-confirmation h2 { font-size: 18px; margin: 18px 0 10px; }
.delete-confirmation p { font-size: 13px; color: var(--muted); line-height: 1.7; overflow-wrap: anywhere; }
.delete-confirmation .delete-note { font-size: 12px; color: var(--theme-danger, #b77878); }
.delete-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }
.delete-actions button { font-size: 12px; }
.delete-submit { color: var(--theme-on-accent, white); background: var(--theme-danger, #bc5252); border-color: var(--theme-danger, #bc5252); }
.delete-submit:hover { background: var(--theme-danger, #a94343); }
.templates-empty { text-align: center; padding: 50px 20px; color: var(--accent); }
.templates-empty h2 { font-size: 15px; color: var(--secondary); margin: 16px 0 8px; }
.templates-empty p { font-size: 12px; color: var(--muted); }
.template-editor { width: 1100px; max-width: 100%; max-height: 92vh; display: flex; flex-direction: column; overflow: hidden; border-radius: 18px; }
.template-editor-heading { display: flex; align-items: center; gap: 12px; padding: 20px 24px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.editor-mark { display: flex; background: var(--accent-soft); color: var(--accent); padding: 11px; border-radius: 11px; }
.template-editor-heading > div { flex: 1; min-width: 0; }
.template-editor-heading h2 { margin: 0; font-size: 17px; overflow-wrap: anywhere; }
.template-editor-heading p { font-size: 11px; color: var(--muted); margin: 5px 0 0; }
.template-editor-body { overflow-y: auto; padding: 22px 24px; min-height: 0; gap: 20px; }
.template-fields { display: grid; grid-template-columns: 2fr 1fr; gap: 14px; }
.template-fields label { font-size: 11px; color: var(--muted); }
.template-fields input { font-size: 13px; border-color: var(--border); }
.description-field { grid-column: 1 / -1; }
.preview-description { color: var(--muted); font-size: 12px; margin: 0; }
.template-editor-footer { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 15px 24px; border-top: 1px solid var(--border); flex-shrink: 0; }
.template-editor-footer > span { font-size: 11px; color: var(--muted); }
.template-editor-footer > div { display: flex; gap: 12px; flex-wrap: wrap; }
.template-editor-footer button { font-size: 12px; }
@media (max-width: 600px) { .templates-heading { align-items: flex-start; flex-wrap: wrap; } .templates-toolbar { flex-wrap: wrap; } .templates-toolbar .search { width: 100%; } .template-fields { grid-template-columns: 1fr; } .template-editor-heading, .template-editor-body, .template-editor-footer { padding: 16px; } .template-editor-footer { flex-wrap: wrap; } .template-editor-footer > div { margin-left: auto; } }
</style>
