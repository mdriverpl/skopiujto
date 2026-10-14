<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { CheckCircle2, Download, ClipboardList, RefreshCw, X, Plus, Search, ArrowUpRight, Trash2 } from 'lucide-vue-next'
const props = defineProps({ api: Function, currentUser: Object, documents: Array, folders: Array, initialTarget: Object, dialogOnly: Boolean })
const emit = defineEmits(['loaded', 'updated', 'open-document', 'open-email', 'open-folder', 'close'])
const data = ref({ mine: [], sent: [], waiting: 0 }), scope = ref('mine'), search = ref(''), statusFilter = ref('all')
const users = ref([]), loading = ref(true), busy = ref(false), error = ref(''), notice = ref(''), draft = ref(null)
const selected = ref(null), confirmed = ref(false), formError = ref('')
const targetType = ref('general')
const targetLabel = computed(() => {
  if (targetType.value === 'folder') {
    const folder = props.folders?.find(item => item.id === draft.value?.folder_id)
    return folder ? `Katalog: ${folderLabel(folder)}` : ''
  }
  if (targetType.value === 'file') {
    const doc = props.documents?.find(item => item.id === draft.value?.document_id)
    return doc ? `Plik: ${doc.filename || doc.title}` : ''
  }
  return 'Zadanie ogólne'
})
function closeDraft() {
  if (busy.value) return
  draft.value = null
  if (props.dialogOnly) emit('close')
}
const availableFolders = computed(() => (props.folders || []).filter(folder => folder.permissions?.read))
function folderLabel(folder) {
  const names = [folder.name], visited = new Set([folder.id])
  let parentId = folder.parent_id
  while (parentId && !visited.has(parentId)) {
    visited.add(parentId)
    const parent = props.folders?.find(item => item.id === parentId)
    if (!parent) break
    names.unshift(parent.name); parentId = parent.parent_id
  }
  return names.join(' / ')
}
const kinds = { general: 'Zadanie', signature: 'Podpisanie dokumentu', modification: 'Modyfikacja dokumentu', approval: 'Akceptacja', deadline: 'Termin dokumentu' }
const labels = { todo: 'Do wykonania', in_progress: 'W toku', done: 'Wykonano', cancelled: 'Anulowano', waiting: 'Oczekuje', accepted: 'Zaakceptowano', expired: 'Wygasło', revoked: 'Cofnięto', failed: 'Błąd wysyłki', sending: 'Wysyłanie' }
const pending = item => ['todo', 'in_progress', 'waiting', 'sending'].includes(item.status)
const filtered = computed(() => data.value[scope.value].filter(item =>
  (statusFilter.value === 'all' || (statusFilter.value === 'open' ? pending(item) : ['done', 'accepted'].includes(item.status))) &&
  `${item.title} ${item.description || ''} ${item.sender_name || ''} ${item.assignee_name || ''}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
let timer, disposed = false, refreshing = false
async function load(silent = false) {
  if (refreshing) return
  refreshing = true
  try { const result = await props.api('/tasks'); if (!disposed) { data.value = result; emit('loaded', result) } }
  catch (err) { if (!silent && !disposed) error.value = err.message }
  finally { loading.value = false; refreshing = false }
}
async function create() {
  if (busy.value || !draft.value) return
  busy.value = true; formError.value = ''
  try {
    if (targetType.value === 'file' && !draft.value.document_id) throw new Error('Wybierz plik lub dokument.')
    if (targetType.value === 'folder' && !draft.value.folder_id) throw new Error('Wybierz katalog.')
    await props.api('/tasks', 'POST', { ...draft.value,
      document_id: targetType.value === 'file' ? draft.value.document_id : null,
      folder_id: targetType.value === 'folder' ? draft.value.folder_id : null,
      due_at: draft.value.due_at ? new Date(draft.value.due_at).toISOString() : null })
    draft.value = null; scope.value = 'sent'; statusFilter.value = 'all'; search.value = ''
    notice.value = 'Zadanie zapisane i przekazane odbiorcy.'
    if (!props.dialogOnly) await load()
    emit('updated')
    if (props.dialogOnly) emit('close')
  } catch (err) { formError.value = err.message }
  finally { busy.value = false }
}
async function newTask() {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const options = await props.api('/sharing-options')
    users.value = [props.currentUser, ...options.users]
    targetType.value = props.initialTarget?.folder_id ? 'folder' : props.initialTarget?.document_id ? 'file' : 'general'
    draft.value = { title: '', description: '', kind: 'general', assignee_id: '',
      document_id: props.initialTarget?.document_id || '', folder_id: props.initialTarget?.folder_id || '', due_at: '' }
    formError.value = ''
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function changeStatus(item, status) {
  if (busy.value || (status === 'cancelled' ? !item.can_cancel : !item.can_update)) return
  if (status === 'cancelled' && !window.confirm('Anulować to zadanie?')) return
  busy.value = true; error.value = ''
  try {
    if (item.origin === 'deadline') {
      if (status !== 'done') return
      await props.api(`/documents/${item.document_id}/deadlines/${item.id}`, 'PATCH', { done: true })
    } else await props.api(`/tasks/${item.id}/status`, 'PATCH', { status, version: item.version })
    await load(); emit('updated')
  }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function deleteTask(item) {
  if (busy.value || item.origin !== 'task' || !item.can_delete) return
  if (!window.confirm('Usunąć zadanie „' + item.title + '”? Zniknie z list autora i odbiorcy. Tej operacji nie można cofnąć.')) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await props.api('/tasks/' + item.id + '?version=' + item.version, 'DELETE')
    await load(); emit('updated')
    notice.value = 'Zadanie zostało usunięte.'
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
function openApproval(item) { if (!busy.value && scope.value === 'mine' && item.can_accept) { selected.value = item; confirmed.value = false; formError.value = '' } }
async function accept() {
  if (busy.value || !selected.value || !confirmed.value) return
  busy.value = true; formError.value = ''
  try {
    await props.api(`/approval-inbox/${selected.value.id}/accept`, 'POST', { confirmed: true })
    selected.value = null; await load(); emit('updated')
  } catch (err) { formError.value = err.message }
  finally { busy.value = false }
}
function openDocument(item) {
  const doc = props.documents?.find(doc => doc.id === item.document_id)
  if (doc) emit(item.origin === 'approval' ? 'open-email' : 'open-document', doc)
}
function openFolder(item) {
  if (availableFolders.value.some(folder => folder.id === item.folder_id)) emit('open-folder', item.folder_id)
}
onMounted(() => {
  if (props.dialogOnly) { newTask(); return }
  load(); timer = setInterval(() => { if (!busy.value && !draft.value && !selected.value) load(true) }, 15000)
})
onBeforeUnmount(() => { disposed = true; clearInterval(timer) })
</script>
<template>
  <section v-if="!dialogOnly" class="tasks-panel"><header class="tasks-heading"><Teleport to="#workspace-title"><div><h1>Zadania <span>{{ data.waiting }}</span></h1><p>Akceptacje, podpisanie dokumentów i zadania od użytkowników.</p></div></Teleport><div class="tasks-actions"><button :disabled="busy || loading" @click="error = ''; load()"><RefreshCw :size="16" /> Odśwież</button><button class="primary" :disabled="busy" @click="newTask"><Plus :size="17" /> Nowe zadanie</button></div></header>
    <div class="tasks-toolbar"><div class="tasks-tabs" role="group" aria-label="Odbiorca zadań"><button :aria-pressed="scope === 'mine'" @click="scope = 'mine'">Zadania dla mnie <span>{{ data.mine.length }}</span></button><button :aria-pressed="scope === 'sent'" @click="scope = 'sent'">Zadania wysłane <span>{{ data.sent.length }}</span></button></div><div class="tasks-search-row"><Teleport to="#workspace-search"><div class="search"><Search :size="17" /><input v-model="search" aria-label="Szukaj zadania" placeholder="Szukaj zadania lub osoby…" /></div></Teleport><select v-model="statusFilter" aria-label="Status zadania"><option value="all">Wszystkie statusy</option><option value="open">Oczekujące i w toku</option><option value="done">Wykonane</option></select></div></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="tasks-notice" role="status">{{ notice }}</p><p v-if="loading" class="muted" role="status">Wczytywanie zadań…</p>
    <div v-else-if="!filtered.length" class="tasks-empty"><ClipboardList :size="34" /><h2>Brak zadań w tym widoku</h2><p>{{ scope === 'mine' ? 'Tutaj pojawią się zadania przypisane do Ciebie i dokumenty wymagające działania.' : 'Tutaj zobaczysz przekazane zadania oraz wysłane prośby o akceptację.' }}</p></div>
    <div class="tasks-list"><article v-for="item in filtered" :key="item.key" class="panel task-item"><span class="task-icon"><ClipboardList :size="22" /></span><div class="task-details"><span class="task-kind">{{ kinds[item.kind] }}</span><h2>{{ item.title }}</h2><p v-if="item.origin === 'task' && item.folder_name">Katalog: {{ item.folder_name }}</p><p v-else-if="item.origin === 'task' && item.document_title">Plik: {{ item.filename || item.document_title }}</p><p v-else-if="item.filename">{{ item.filename }}<template v-if="item.file_version"> · v{{ item.file_version }}</template></p><small>{{ scope === 'mine' ? `Od: ${item.sender_name}` : `Dla: ${item.assignee_name}` }}<template v-if="scope === 'sent' && item.channel"> · {{ { email: 'E-mail', sms: 'SMS', user: 'Aplikacja' }[item.channel] }}</template> · {{ date(item.created_at) }}</small><p v-if="item.description" class="task-description">{{ item.description }}</p><small v-if="item.due_at" :class="{ overdue: pending(item) && new Date(item.due_at).getTime() < Date.now() }">Termin: {{ date(item.due_at) }}</small><small v-if="item.completed_at">Zakończono {{ date(item.completed_at) }}</small></div><div class="task-actions"><span class="task-status" :class="item.status">{{ labels[item.status] }}</span><button v-if="item.document_id && documents?.some(doc => doc.id === item.document_id)" :disabled="busy" @click="openDocument(item)"><ArrowUpRight :size="15" /> {{ item.origin === 'approval' ? 'Historia akceptacji' : 'Otwórz dokument' }}</button><button v-if="item.folder_id && availableFolders.some(folder => folder.id === item.folder_id)" :disabled="busy" @click="openFolder(item)"><ArrowUpRight :size="15" /> Otwórz katalog</button><a v-if="scope === 'mine' && item.can_download" :href="`/api/approval-inbox/${item.id}/file`"><Download :size="16" /> Pobierz plik</a><button v-if="scope === 'mine' && item.can_accept" class="primary" :disabled="busy" @click="openApproval(item)"><CheckCircle2 :size="16" /> Akceptuj</button><template v-if="scope === 'mine' && item.can_update"><button v-if="item.origin === 'task' && item.status === 'todo'" :disabled="busy" @click="changeStatus(item, 'in_progress')">Rozpocznij</button><button class="primary" :disabled="busy" @click="changeStatus(item, 'done')"><CheckCircle2 :size="16" /> Zakończ zadanie</button></template><button v-if="item.origin === 'task' && item.can_cancel" class="cancel-task" :disabled="busy" @click="changeStatus(item, 'cancelled')">Anuluj zadanie</button><button v-if="item.origin === 'task' && item.can_delete" class="cancel-task" :disabled="busy" @click="deleteTask(item)"><Trash2 :size="15" /> Usuń zadanie</button></div></article></div>
  </section>
  <div v-if="dialogOnly && !draft" class="modal-backdrop"><section class="panel approval-confirm" role="dialog" aria-modal="true" aria-label="Nowe zadanie"><div class="editor-heading"><h2>Nowe zadanie</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="closeDraft"><X :size="20" /></button></div><p v-if="error" class="error" role="alert">{{ error }}</p><p v-else class="muted">Wczytywanie…</p><button v-if="error" :disabled="busy" @click="newTask">Spróbuj ponownie</button></section></div>
  <div v-if="draft" class="modal-backdrop"><section class="panel task-dialog" role="dialog" aria-modal="true" aria-labelledby="new-task-title"><header class="editor-heading"><h2 id="new-task-title">Dodaj zadanie</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="closeDraft"><X :size="20" /></button></header><form @submit.prevent="create"><div class="task-form-body"><p v-if="formError" class="error" role="alert">{{ formError }}</p><p v-if="targetLabel" class="task-target">{{ targetLabel }}</p><label class="task-recipient">Dla kogo<select aria-label="Dla kogo przypisać zadanie" autofocus v-model="draft.assignee_id" required :disabled="busy"><option disabled value="">Wybierz osobę…</option><option v-for="person in users" :key="person.id" :value="person.id">{{ person.name }}{{ person.id === currentUser.id ? ' (ja)' : '' }}</option></select></label><label>Tytuł zadania<input v-model="draft.title" required maxlength="200" :disabled="busy" placeholder="np. Podpisz umowę z kontrahentem" /></label><div><label>Rodzaj<select v-model="draft.kind" :disabled="busy"><option value="general">Zadanie ogólne</option><option value="signature">Podpisanie dokumentu</option><option value="modification">Modyfikacja dokumentu</option></select></label></div><label>Opis zadania <span class="optional">opcjonalnie</span><textarea v-model="draft.description" aria-label="Opis zadania" maxlength="5000" rows="5" :disabled="busy" placeholder="Opisz, co należy zrobić, jaki ma być efekt i na co zwrócić uwagę." /></label><label>Powiązanie zadania<select v-model="targetType" :disabled="busy"><option value="general">Ogólne</option><option value="folder">Katalog</option><option value="file">Plik lub dokument</option></select></label><label v-if="targetType === 'folder'">Katalog<select v-model="draft.folder_id" required :disabled="busy"><option disabled value="">Wybierz katalog…</option><option v-for="folder in availableFolders" :key="folder.id" :value="folder.id">{{ folderLabel(folder) }}</option></select></label><label v-if="targetType === 'file'">Plik lub dokument<select v-model="draft.document_id" required :disabled="busy"><option disabled value="">Wybierz plik lub dokument…</option><option v-for="doc in documents" :key="doc.id" :value="doc.id">{{ doc.filename || doc.title }}</option></select></label><label>Termin <span class="optional">opcjonalnie</span><input v-model="draft.due_at" type="datetime-local" :disabled="busy" /></label></div><footer class="editor-actions"><button type="button" :disabled="busy" @click="closeDraft">Anuluj</button><button class="primary" type="submit" :disabled="busy || !draft.assignee_id || !draft.title.trim()"><Plus :size="16" /> {{ busy ? 'Zapisywanie…' : 'Dodaj zadanie' }}</button></footer></form></section></div>
  <div v-if="selected" class="modal-backdrop"><section class="panel approval-confirm" role="dialog" aria-modal="true" aria-labelledby="task-approval-title"><div class="editor-heading"><h2 id="task-approval-title">Akceptacja pliku</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="selected = null"><X :size="20" /></button></div><p><strong>{{ selected.filename }}</strong> · wersja {{ selected.file_version }}</p><p class="muted">Od: {{ selected.sender_name }}</p><a :href="`/api/approval-inbox/${selected.id}/file`"><Download :size="16" /> Pobierz przesłaną wersję</a><p v-if="formError" class="error" role="alert">{{ formError }}</p><form @submit.prevent="accept"><label class="check-label"><input v-model="confirmed" type="checkbox" :disabled="busy" required /> Potwierdzam, że zapoznałem/am się z plikiem i akceptuję wersję {{ selected.file_version }}.</label><div class="editor-actions"><button type="button" :disabled="busy" @click="selected = null">Anuluj</button><button class="primary" type="submit" :disabled="busy || !confirmed"><CheckCircle2 :size="16" /> {{ busy ? 'Zapisywanie…' : 'Akceptuję plik' }}</button></div></form></section></div>
</template>
<style scoped>
.task-recipient { padding: 16px; border: 1px solid var(--theme-accent-soft, #e4dfff); border-radius: 12px; background: var(--theme-accent-soft, #faf9ff); color: var(--accent); }.task-target { margin: 0; font-size: 12px; color: var(--secondary); overflow-wrap: anywhere; }

.tasks-heading, .tasks-actions, .tasks-tabs, .tasks-search-row { display: flex; align-items: center; gap: 12px; }.tasks-heading { justify-content: space-between; margin: 24px 0; flex-wrap: wrap; }h1 { margin: 0; font-size: 25px; }h1 span { font-size: 12px; padding: 4px 8px; background: var(--accent-soft); color: var(--accent); border-radius: 8px; vertical-align: middle; }.tasks-heading p { color: var(--muted); font-size: 12px; margin: 8px 0 0; }.tasks-tabs { gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }.tasks-tabs button { border-color: transparent; background: transparent; color: var(--muted); font-size: 13px; }.tasks-tabs button[aria-pressed='true'] { color: var(--accent); background: var(--accent-soft); }.tasks-tabs span { font-size: 11px; opacity: .7; }.tasks-search-row { justify-content: space-between; flex-wrap: wrap; margin-bottom: 22px; }.tasks-search-row .search { flex: 1; max-width: 550px; }.tasks-search-row select { width: auto; font-size: 12px; }.tasks-list { display: grid; gap: 14px; }.task-item { display: flex; gap: 16px; align-items: flex-start; padding: 20px; border-radius: 14px; }.task-icon { background: var(--accent-soft); color: var(--accent); padding: 12px; border-radius: 12px; display: flex; }.task-details { flex: 1; min-width: 0; overflow-wrap: anywhere; }.task-details h2 { font-size: 15px; margin: 6px 0; }.task-details p { font-size: 12px; margin: 6px 0; color: var(--secondary); }.task-kind { color: var(--accent); font-size: 10px; }.task-details small { color: var(--muted); font-size: 11px; display: block; margin-top: 6px; }.task-description { white-space: pre-wrap; }.task-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; font-size: 12px; flex-shrink: 0; }.task-actions a, .approval-confirm a { display: inline-flex; align-items: center; gap: 6px; }.task-actions button { font-size: 11px; }.task-status { font-size: 11px; padding: 5px 8px; border-radius: 7px; color: var(--muted); background: var(--surface-soft); }.task-status.waiting, .task-status.todo { color: var(--warning); background: var(--warning-soft); }.task-status.accepted, .task-status.done { color: var(--success); background: var(--success-soft); }.task-status.in_progress { color: var(--accent); background: var(--accent-soft); }.task-details .overdue { color: var(--danger); }.cancel-task { color: var(--danger); border: none; background: transparent; padding: 5px; }.tasks-empty { padding: 50px 20px; text-align: center; color: var(--muted); }.tasks-empty h2 { font-size: 17px; }.tasks-empty p { font-size: 13px; }.tasks-notice { color: var(--success); font-size: 13px; }.task-dialog { width: min(700px, 100%); max-height: 90dvh; padding: 0; display: flex; flex-direction: column; overflow: hidden; }.task-dialog > header { padding: 20px 24px; border-bottom: 1px solid var(--border); flex-shrink: 0; }.task-dialog form { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }.task-form-body { overflow-y: auto; min-height: 0; padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }.task-dialog footer { flex-shrink: 0; padding: 16px 24px; border-top: 1px solid var(--border); margin: 0; }.optional { color: var(--muted); font-size: 11px; }.approval-confirm { max-width: 540px; overflow-wrap: anywhere; }.approval-confirm h2, .task-dialog h2 { font-size: 19px; margin: 0; }.approval-confirm form { margin-top: 20px; }.approval-confirm .check-label { align-items: flex-start; line-height: 1.6; font-size: 13px; }.approval-confirm .check-label input { margin-top: 5px; }@media (max-width: 600px) { .task-item { flex-wrap: wrap; gap: 12px; }.task-actions { flex-direction: row; align-items: center; justify-content: flex-end; flex-wrap: wrap; width: 100%; }.tasks-heading h1 { font-size: 22px; }.task-form-body, .task-dialog > header, .task-dialog footer { padding: 16px; } }
</style>
