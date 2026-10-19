<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { CheckCircle2, Download, ClipboardList, RefreshCw, X, Plus, Search, ArrowUpRight, Trash2, List, LayoutGrid, Grid3X3, UserRound, FolderCheck, Folder, ChevronRight } from 'lucide-vue-next'
import TaskMessageSource from './TaskMessageSource.vue'
import TaskStatusMenu from './TaskStatusMenu.vue'
const props = defineProps({ api: Function, currentUser: Object, documents: Array, folders: Array, initialTarget: Object, dialogOnly: Boolean })
const emit = defineEmits(['loaded', 'updated', 'open-document', 'open-email', 'open-folder', 'open-message', 'close'])
const data = ref({ mine: [], sent: [], waiting: 0 }), scope = ref('mine'), search = ref(''), statusFilter = ref('all')
const users = ref([]), loading = ref(true), busy = ref(false), error = ref(''), notice = ref(''), draft = ref(null)
const selected = ref(null), confirmed = ref(false), formError = ref('')
const previewKey = ref(null), previewDialog = ref(null)
const previewTask = computed(() => [...data.value.mine, ...data.value.sent].find(item => item.key === previewKey.value))
function openTask(item) {
  if (busy.value) return
  previewKey.value = item.key
  previewDialog.value?.showModal()
}
function closeTask() {
  previewDialog.value?.close()
  previewKey.value = null
}
function openSourceMail(message) {
  closeTask()
  emit('open-message', message)
}
function clickTask(item, event) {
  if (!event.target.closest('button, a, select, input, textarea, label')) openTask(item)
}
const layout = ref('list')
const layoutKey = `edokumenty-task-layout:${props.currentUser?.id || 'default'}`
try {
  const saved = localStorage.getItem(layoutKey)
  if (['list', 'grid', 'icons'].includes(saved)) layout.value = saved
} catch {}
function changeLayout(value) {
  if (!['list', 'grid', 'icons'].includes(value)) return
  layout.value = value
  try { localStorage.setItem(layoutKey, value) } catch {}
}
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
const previewFolder = computed(() => availableFolders.value.find(folder => folder.id === previewTask.value?.folder_id))
function openPreviewFolder() {
  if (busy.value || !previewFolder.value) return
  const folderId = previewFolder.value.id
  closeTask()
  emit('open-folder', folderId)
}
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
const kinds = { folder_completion: 'Uzupełnienie katalogu', general: 'Zadanie', signature: 'Podpisanie dokumentu', modification: 'Modyfikacja dokumentu', approval: 'Akceptacja', deadline: 'Termin dokumentu' }
const labels = { todo: 'Do wykonania', in_progress: 'W toku', done: 'Wykonano', cancelled: 'Anulowano', waiting: 'Oczekuje', accepted: 'Zaakceptowano', expired: 'Wygasło', revoked: 'Cofnięto', failed: 'Błąd wysyłki', sending: 'Wysyłanie' }
function statusOptions(item) {
  const statuses = [item.status]
  if (item.origin === 'task') {
    if (item.can_update) statuses.push('in_progress', 'done')
    if (item.can_cancel) statuses.push('cancelled')
  } else if (item.origin === 'deadline' && item.can_update) statuses.push('done')
  return [...new Set(statuses)].map(value => ({ value, label: labels[value] || value }))
}
const pending = item => ['todo', 'in_progress', 'waiting', 'sending'].includes(item.status)
function taskSender(item) {
  const client = item.client
  if (client?.email) return client.name && client.name !== client.email ? `${client.name} <${client.email}>` : client.email
  return item.source_message?.sender || item.sender_name || '—'
}
function clientLabel(item) {
  return [item.client?.company, item.client?.name, item.client?.email].filter((value, index, values) => value && values.indexOf(value) === index).join(' · ')
}
const filtered = computed(() => data.value[scope.value].filter(item =>
  (statusFilter.value === 'all' || (statusFilter.value === 'open' ? pending(item) : ['done', 'accepted'].includes(item.status))) &&
  `${item.title} ${item.description || ''} ${item.sender_name || ''} ${item.assignee_name || ''} ${taskSender(item)} ${clientLabel(item)}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
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
    draft.value = { title: '', description: '', kind: props.initialTarget?.folder_id ? 'folder_completion' : 'general', assignee_id: '',
      document_id: props.initialTarget?.document_id || '', folder_id: props.initialTarget?.folder_id || '', due_at: '' }
    formError.value = ''
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function changeStatus(item, status) {
  if (busy.value || status === item.status || !statusOptions(item).some(option => option.value === status) ||
      (status === 'cancelled' ? !item.can_cancel : !item.can_update)) return
  if (status === 'cancelled' && !window.confirm('Anulować to zadanie?')) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (item.origin === 'deadline') {
      if (status !== 'done') return
      await props.api(`/documents/${item.document_id}/deadlines/${item.id}`, 'PATCH', { done: true })
    } else {
      const result = await props.api(`/tasks/${item.id}/status`, 'PATCH', { status, version: item.version })
      if (result?.notification?.status === 'failed') {
        notice.value = 'Status zadania zmieniono. Powiadomienie e-mail nie zostało wysłane i czeka w folderze Robocze autora zadania.'
        error.value = result.notification.message
      } else if (result?.notification?.status === 'sent') {
        notice.value = 'Status zadania zmieniono. Powiadomienie e-mail zostało wysłane.'
      }
    }
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
  <section v-if="!dialogOnly" class="tasks-panel"><div class="page-menu"><header class="tasks-heading"><Teleport to="#workspace-title"><div><h1>Zadania <span>{{ data.waiting }}</span></h1><p>Akceptacje, podpisanie dokumentów i zadania od użytkowników.</p></div></Teleport><div class="tasks-actions"><button :disabled="busy || loading" @click="error = ''; load()"><RefreshCw :size="16" /> Odśwież</button><button class="primary" :disabled="busy" @click="newTask"><Plus :size="17" /> Nowe zadanie</button></div></header>
    <div class="tasks-toolbar"><div class="tasks-tabs" role="group" aria-label="Odbiorca zadań"><button :aria-pressed="scope === 'mine'" @click="scope = 'mine'">Zadania dla mnie <span>{{ data.mine.length }}</span></button><button :aria-pressed="scope === 'sent'" @click="scope = 'sent'">Zadania wysłane <span>{{ data.sent.length }}</span></button></div><div class="tasks-search-row"><div class="layout-switch" role="group" aria-label="Widok zadań"><button :aria-pressed="layout === 'list'" aria-label="Widok listy" title="Lista" @click="changeLayout('list')"><List :size="18" /> Lista</button><button :aria-pressed="layout === 'grid'" aria-label="Widok kafelków" title="Kafelki" @click="changeLayout('grid')"><LayoutGrid :size="18" /> Kafelki</button><button :aria-pressed="layout === 'icons'" aria-label="Widok ikon" title="Ikony" @click="changeLayout('icons')"><Grid3X3 :size="18" /> Ikony</button></div><Teleport to="#workspace-search"><div class="search"><Search :size="17" /><input v-model="search" aria-label="Szukaj zadania" placeholder="Szukaj zadania lub osoby…" /></div></Teleport><select v-model="statusFilter" aria-label="Status zadania"><option value="all">Wszystkie statusy</option><option value="open">Oczekujące i w toku</option><option value="done">Wykonane</option></select></div></div></div>

    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="tasks-notice" role="status">{{ notice }}</p><p v-if="loading" class="muted" role="status">Wczytywanie zadań…</p>
    <div v-else-if="!filtered.length" class="tasks-empty"><ClipboardList :size="34" /><h2>Brak zadań w tym widoku</h2><p>{{ scope === 'mine' ? 'Tutaj pojawią się zadania przypisane do Ciebie i dokumenty wymagające działania.' : 'Tutaj zobaczysz przekazane zadania oraz wysłane prośby o akceptację.' }}</p></div>
    <div class="tasks-list" :class="{ 'tasks-grid': layout === 'grid', 'tasks-icons': layout === 'icons' }"><article v-for="item in filtered" :key="item.key" class="panel task-item" @click="clickTask(item, $event)"><span class="task-icon"><ClipboardList :size="22" /></span><div class="task-details"><span class="task-kind">{{ kinds[item.kind] }}</span><h2 :title="item.title"><button type="button" class="task-preview-trigger" aria-haspopup="dialog" :disabled="busy" @click.stop="openTask(item)">{{ item.title }}</button></h2><p v-if="item.client" class="task-client-summary" :title="clientLabel(item)"><UserRound :size="12" />{{ clientLabel(item) }}</p><p v-if="item.origin === 'task' && item.folder_name">Katalog: {{ item.folder_name }}</p><p v-else-if="item.origin === 'task' && item.document_title">Plik: {{ item.filename || item.document_title }}</p><p v-else-if="item.filename">{{ item.filename }}<template v-if="item.file_version"> · v{{ item.file_version }}</template></p><small>{{ scope === 'mine' ? `Od: ${taskSender(item)}` : `Dla: ${item.assignee_name}` }}<template v-if="scope === 'sent' && item.channel"> · {{ { email: 'E-mail', sms: 'SMS', user: 'Aplikacja' }[item.channel] }}</template> · {{ date(item.created_at) }}</small><p v-if="item.description" class="task-description" :title="item.description">{{ item.description }}</p><small class="task-due" v-if="item.due_at" :class="{ overdue: pending(item) && new Date(item.due_at).getTime() < Date.now() }">Termin: {{ date(item.due_at) }}</small><small v-if="item.completed_at">Zakończono {{ date(item.completed_at) }}</small></div><div class="task-status-control"><TaskStatusMenu v-if="statusOptions(item).length > 1" :status="item.status" :label="labels[item.status]" :title="item.title" :options="statusOptions(item)" :busy="busy" @change="changeStatus(item, $event)" /><span v-else class="task-status" :class="item.status">{{ labels[item.status] }}</span></div><div class="task-actions"><button v-if="item.document_id && documents?.some(doc => doc.id === item.document_id)" :disabled="busy" title="Otwórz dokument" @click="openDocument(item)"><ArrowUpRight :size="15" /> {{ item.origin === 'approval' ? 'Historia akceptacji' : 'Otwórz dokument' }}</button><button v-if="item.folder_id && availableFolders.some(folder => folder.id === item.folder_id)" :disabled="busy" title="Otwórz katalog" @click="openFolder(item)"><ArrowUpRight :size="15" /> Otwórz katalog</button><a v-if="scope === 'mine' && item.can_download" title="Pobierz plik" :href="`/api/approval-inbox/${item.id}/file`"><Download :size="16" /> Pobierz plik</a><button v-if="scope === 'mine' && item.can_accept" class="primary" :disabled="busy" title="Akceptuj" @click="openApproval(item)"><CheckCircle2 :size="16" /> Akceptuj</button><button v-if="item.origin === 'task' && item.can_delete" class="delete-task" :aria-label="`Usuń zadanie: ${item.title}`" :disabled="busy" title="Usuń zadanie" @click="deleteTask(item)"><Trash2 :size="15" /> Usuń zadanie</button></div></article></div>
  </section>
  <div v-if="dialogOnly && !draft" class="modal-backdrop"><section class="panel approval-confirm" role="dialog" aria-modal="true" aria-label="Nowe zadanie"><div class="editor-heading"><h2>Nowe zadanie</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="closeDraft"><X :size="20" /></button></div><p v-if="error" class="error" role="alert">{{ error }}</p><p v-else class="muted">Wczytywanie…</p><button v-if="error" :disabled="busy" @click="newTask">Spróbuj ponownie</button></section></div>
  <div v-if="draft" class="modal-backdrop"><section class="panel task-dialog" role="dialog" aria-modal="true" aria-labelledby="new-task-title"><header class="editor-heading"><h2 id="new-task-title">Dodaj zadanie</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="closeDraft"><X :size="20" /></button></header><form @submit.prevent="create"><div class="task-form-body"><p v-if="formError" class="error" role="alert">{{ formError }}</p><p v-if="targetLabel" class="task-target">{{ targetLabel }}</p><label class="task-recipient">Dla kogo<select aria-label="Dla kogo przypisać zadanie" autofocus v-model="draft.assignee_id" required :disabled="busy"><option disabled value="">Wybierz osobę…</option><option v-for="person in users" :key="person.id" :value="person.id">{{ person.name }}{{ person.id === currentUser.id ? ' (ja)' : '' }}</option></select></label><label>Tytuł zadania<input v-model="draft.title" required maxlength="200" :disabled="busy" placeholder="np. Podpisz umowę z kontrahentem" /></label><div v-if="!initialTarget?.folder_id"><label>Rodzaj<select v-model="draft.kind" :disabled="busy"><option value="general">Zadanie ogólne</option><option value="folder_completion">Uzupełnienie katalogu</option><option value="signature">Podpisanie dokumentu</option><option value="modification">Modyfikacja dokumentu</option></select></label></div><label><span class="task-field-caption">Opis zadania <span class="optional">opcjonalnie</span></span><textarea v-model="draft.description" aria-label="Opis zadania" maxlength="5000" rows="3" :disabled="busy" placeholder="Opisz, co należy zrobić, jaki ma być efekt i na co zwrócić uwagę." /></label><label><span class="task-field-caption">Termin <span class="optional">opcjonalnie</span></span><input v-model="draft.due_at" type="datetime-local" :disabled="busy" /></label></div><footer class="editor-actions"><button type="button" :disabled="busy" @click="closeDraft">Anuluj</button><button class="primary" type="submit" :disabled="busy || !draft.assignee_id || !draft.title.trim()"><Plus :size="16" /> {{ busy ? 'Zapisywanie…' : 'Dodaj zadanie' }}</button></footer></form></section></div>
  <div v-if="selected" class="modal-backdrop"><section class="panel approval-confirm" role="dialog" aria-modal="true" aria-labelledby="task-approval-title"><div class="editor-heading"><h2 id="task-approval-title">Akceptacja pliku</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="selected = null"><X :size="20" /></button></div><p><strong>{{ selected.filename }}</strong> · wersja {{ selected.file_version }}</p><p class="muted">Od: {{ selected.sender_name }}</p><a :href="`/api/approval-inbox/${selected.id}/file`"><Download :size="16" /> Pobierz przesłaną wersję</a><p v-if="formError" class="error" role="alert">{{ formError }}</p><form @submit.prevent="accept"><label class="check-label"><input v-model="confirmed" type="checkbox" :disabled="busy" required /> Potwierdzam, że zapoznałem/am się z plikiem i akceptuję wersję {{ selected.file_version }}.</label><div class="editor-actions"><button type="button" :disabled="busy" @click="selected = null">Anuluj</button><button class="primary" type="submit" :disabled="busy || !confirmed"><CheckCircle2 :size="16" /> {{ busy ? 'Zapisywanie…' : 'Akceptuję plik' }}</button></div></form></section></div>
  <dialog ref="previewDialog" class="task-preview" aria-labelledby="task-preview-title" @close="previewKey = null" @cancel="previewKey = null" @click="($event.target === previewDialog) && closeTask()">
    <header><span class="task-preview-art" aria-hidden="true"><FolderCheck v-if="previewTask?.kind === 'folder_completion'" :size="30" :stroke-width="1.5" /><ClipboardList v-else :size="30" :stroke-width="1.5" /></span><div class="task-preview-heading"><span class="task-kind">{{ kinds[previewTask?.kind] }}</span><h2 id="task-preview-title">{{ previewTask?.title }}</h2></div><button type="button" class="icon-button" aria-label="Zamknij podgląd zadania" title="Zamknij" @click="closeTask"><X :size="20" /></button></header>
    <div v-if="previewTask" class="task-preview-body">
      <section v-if="previewTask.client" class="task-client-card" aria-label="Klient"><UserRound :size="23" /><div><small>Klient</small><strong>{{ previewTask.client.company || (previewTask.client.name !== previewTask.client.email && previewTask.client.name) || 'Klient' }}</strong><span v-if="previewTask.client.company && previewTask.client.name && previewTask.client.name !== previewTask.client.email && previewTask.client.name !== previewTask.client.company">{{ previewTask.client.name }}</span><a v-if="previewTask.client.email" :href="`mailto:${previewTask.client.email}`">{{ previewTask.client.email }}</a></div></section>

      <button v-if="previewFolder" type="button" class="task-folder-link" :disabled="busy" :aria-label="`Otwórz katalog: ${previewFolder.name}`" @click="openPreviewFolder"><span class="task-folder-icon" aria-hidden="true"><Folder :size="25" :stroke-width="1.5" /></span><span class="task-folder-label"><small>Katalog zadania</small><strong>{{ folderLabel(previewFolder) }}</strong><span>Otwórz katalog</span></span><ChevronRight :size="18" aria-hidden="true" /></button>
      <p v-else-if="previewTask.folder_name" class="task-preview-resource">Katalog: {{ previewTask.folder_name }}</p><p v-if="previewTask.filename || previewTask.document_title" class="task-preview-resource">Plik: {{ previewTask.filename || previewTask.document_title }}<template v-if="previewTask.file_version"> · v{{ previewTask.file_version }}</template></p>
      <TaskMessageSource v-if="previewTask.source_message" :key="previewTask.key" :api="api" :task-id="previewTask.id" :source="previewTask.source_message" @open-mail="openSourceMail" />
      <section class="task-preview-content"><h3>Treść zadania</h3><p class="task-preview-description">{{ previewTask.description || 'Brak dodatkowej treści.' }}</p></section>
      <dl class="task-preview-meta"><div><dt>Termin realizacji</dt><dd>{{ previewTask.due_at ? date(previewTask.due_at) : 'Nie ustalono' }}</dd></div><div><dt>Utworzył zadanie</dt><dd>{{ previewTask.sender_name || '—' }}</dd></div><div><dt>Wykonawca</dt><dd>{{ previewTask.assignee_name || '—' }}</dd></div><div><dt>Utworzono</dt><dd>{{ date(previewTask.created_at) }}</dd></div><div v-if="previewTask.completed_at"><dt>Zakończono</dt><dd>{{ date(previewTask.completed_at) }}</dd></div></dl>
    </div>
    <footer><div v-if="previewTask" class="task-preview-footer-status"><span>Status</span><span class="task-status" :class="previewTask.status">{{ labels[previewTask.status] }}</span></div><button type="button" @click="closeTask">Zamknij</button></footer>
  </dialog>
</template>
<style scoped>
.task-client-summary { color:var(--accent)!important; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }.task-client-summary svg { vertical-align:-2px; margin-right:5px; }
.task-client-card { display:flex; align-items:flex-start; gap:12px; padding:16px; margin-bottom:24px; border:1px solid var(--border); border-radius:12px; background:var(--accent-soft); }.task-client-card > svg { flex-shrink:0; margin-top:3px; color:var(--accent); }.task-client-card > div { display:grid; gap:6px; min-width:0; overflow-wrap:anywhere; }.task-client-card small { font-size:11px; color:var(--muted); }.task-client-card strong { font-size:15px; }.task-client-card span,.task-client-card a { font-size:13px; }.task-client-card a { color:var(--accent); }
.tasks-icons .task-details > .task-client-summary { display:block; margin:4px 0 0; font-size:10px; }
.task-item { cursor:pointer; }
.task-preview-trigger { display:inline; padding:0; border:0; border-radius:3px; background:transparent; color:inherit; font:inherit; font-weight:inherit; text-align:left; line-height:inherit; overflow-wrap:anywhere; }
.task-preview-trigger:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
.tasks-grid .task-preview-trigger { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; line-clamp:2; overflow:hidden; }
.task-preview { width:min(640px,calc(100vw - 32px)); max-height:90dvh; box-sizing:border-box; padding:0; border:1px solid var(--border); border-radius:18px; color:var(--text); background:var(--surface); box-shadow:0 25px 80px #0003; }
.task-preview[open] { display:flex; flex-direction:column; }
.task-preview::backdrop { background:#13213966; backdrop-filter:blur(5px); }
.task-preview > header { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; padding:22px 24px; border-bottom:1px solid var(--border); flex-shrink:0; }
.task-preview header > div { min-width:0; flex:1; }.task-preview h2 { margin:7px 0 0; font-size:20px; line-height:1.5; overflow-wrap:anywhere; }.task-preview header button { flex-shrink:0; }
.task-preview-body { padding:24px; overflow:auto; min-height:0; }.task-preview-meta { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin:0 0 24px; }.task-preview-meta dt { margin-bottom:8px; color:var(--muted); font-size:12px; }.task-preview-meta dd { margin:0; font-size:13px; overflow-wrap:anywhere; }.task-preview h3 { font-size:14px; margin:24px 0 12px; }.task-preview-description { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.8; font-size:14px; margin:0; }.task-preview-resource { font-size:13px; color:var(--secondary); overflow-wrap:anywhere; }
.task-preview footer { display:flex; justify-content:flex-end; padding:16px 24px; border-top:1px solid var(--border); flex-shrink:0; }
@media(max-width:600px) { .task-preview { width:calc(100vw - 20px); max-height:94dvh; }.task-preview > header,.task-preview-body,.task-preview footer { padding:16px; }.task-preview-meta { gap:16px; } }
.task-recipient { color: var(--secondary); }.task-target { margin: 0; font-size: 12px; color: var(--secondary); overflow-wrap: anywhere; }

.tasks-heading, .tasks-actions, .tasks-tabs, .tasks-search-row { display: flex; align-items: center; gap: 12px; }.tasks-heading { justify-content: space-between; margin: 24px 0; flex-wrap: wrap; }h1 { margin: 0; font-size: 25px; }h1 span { font-size: 12px; padding: 4px 8px; background: var(--accent-soft); color: var(--accent); border-radius: 8px; vertical-align: middle; }.tasks-heading p { color: var(--muted); font-size: 12px; margin: 8px 0 0; }.tasks-tabs { gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }.tasks-tabs button { border-color: transparent; background: transparent; color: var(--muted); font-size: 13px; }.tasks-tabs button[aria-pressed='true'] { color: var(--accent); background: var(--accent-soft); }.tasks-tabs span { font-size: 11px; opacity: .7; }.tasks-search-row { justify-content: space-between; flex-wrap: wrap; margin-bottom: 22px; }.tasks-search-row .search { flex: 1; max-width: 550px; }.tasks-search-row select { width: auto; font-size: 12px; }.tasks-list { display: grid; gap: 14px; }.task-item { display: flex; gap: 16px; align-items: flex-start; padding: 20px; border-radius: 14px; }.task-icon { background: var(--accent-soft); color: var(--accent); padding: 12px; border-radius: 12px; display: flex; }.task-details { flex: 1; min-width: 0; overflow-wrap: anywhere; }.task-details h2 { font-size: 15px; margin: 6px 0; }.task-details p { font-size: 12px; margin: 6px 0; color: var(--secondary); }.task-kind { color: var(--accent); font-size: 10px; }.task-details small { color: var(--muted); font-size: 11px; display: block; margin-top: 6px; }.task-description { white-space: pre-wrap; }.task-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; font-size: 12px; flex-shrink: 0; }.task-actions a, .approval-confirm a { display: inline-flex; align-items: center; gap: 6px; }.task-actions button { font-size: 11px; }.task-status { font-size: 11px; padding: 5px 8px; border-radius: 7px; color: var(--muted); background: var(--surface-soft); }.task-status.waiting, .task-status.todo { color: var(--warning); background: var(--warning-soft); }.task-status.accepted, .task-status.done { color: var(--success); background: var(--success-soft); }.task-status.in_progress { color: var(--accent); background: var(--accent-soft); }.task-details .overdue { color: var(--danger); }.cancel-task { color: var(--danger); border: none; background: transparent; padding: 5px; }.tasks-empty { padding: 50px 20px; text-align: center; color: var(--muted); }.tasks-empty h2 { font-size: 17px; }.tasks-empty p { font-size: 13px; }.tasks-notice { color: var(--success); font-size: 13px; }.task-dialog { width: min(520px, 100%); max-height: 90dvh; padding: 0; display: flex; flex-direction: column; overflow: hidden; }.task-dialog > header { padding: 14px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0; }.task-dialog form { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }.task-form-body { overflow-y: auto; min-height: 0; padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }.task-dialog footer { flex-shrink: 0; padding: 12px 20px; border-top: 1px solid var(--border); margin: 0; }.optional { color: var(--muted); font-size: 11px; }.approval-confirm { max-width: 540px; overflow-wrap: anywhere; }.approval-confirm h2, .task-dialog h2 { font-size: 19px; margin: 0; }.approval-confirm form { margin-top: 20px; }.approval-confirm .check-label { align-items: flex-start; line-height: 1.6; font-size: 13px; }.approval-confirm .check-label input { margin-top: 5px; }@media (max-width: 600px) { .task-item { flex-wrap: wrap; gap: 12px; }.task-actions { flex-direction: row; align-items: center; justify-content: flex-end; flex-wrap: wrap; width: 100%; }.tasks-heading h1 { font-size: 22px; }.task-form-body, .task-dialog > header, .task-dialog footer { padding: 16px; } }
.task-item { display:grid; grid-template-columns:46px minmax(180px,1fr) 160px minmax(180px,.7fr); align-items:start; }
.task-icon { justify-content:center; }
.task-status-control { min-width:0; }
.task-actions { min-width:0; flex-shrink:1; flex-direction:row; justify-content:flex-end; align-items:center; flex-wrap:wrap; }
.task-actions button, .task-actions a { white-space:normal; text-align:left; }
.task-actions .delete-task { color:var(--theme-danger,#ba253b); border:1px solid var(--border); background:var(--surface); padding:8px 10px; }
.task-actions .delete-task:hover { background:var(--danger-soft); }
.tasks-grid { grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr)); align-items:stretch; }
.tasks-grid .task-item { box-sizing:border-box; height:340px; min-height:340px; grid-template-columns:46px minmax(0,1fr); grid-template-rows:minmax(0,1fr) auto auto; overflow:hidden; }
.tasks-grid .task-details { min-height:0; height:100%; overflow:hidden; }
.tasks-grid .task-details h2 { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; line-clamp:2; line-height:1.4; overflow:hidden; }
.tasks-grid .task-description { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:3; line-clamp:3; line-height:1.5; overflow:hidden; }
.tasks-grid .task-details > p:not(.task-description),.tasks-grid .task-details small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.tasks-grid .task-status-control { grid-column:1 / -1; }
.tasks-grid .task-actions { grid-column:1 / -1; align-self:end; justify-content:flex-start; padding-top:12px; border-top:1px solid var(--border); }
.tasks-icons { grid-template-columns:repeat(auto-fill,minmax(min(100%,160px),1fr)); gap:12px; }
.tasks-icons .task-item { box-sizing:border-box; height:220px; min-height:220px; grid-template-columns:minmax(0,1fr); grid-template-rows:36px minmax(0,1fr) 28px 30px; gap:8px; padding:14px; text-align:center; overflow:hidden; }
.tasks-icons .task-icon { justify-self:center; padding:7px; border-radius:9px; }
.tasks-icons .task-details { min-height:0; overflow:hidden; }
.tasks-icons .task-kind,.tasks-icons .task-details > p,.tasks-icons .task-details small:not(.task-due) { display:none; }
.tasks-icons .task-details h2 { margin:0; font-size:12px; line-height:1.4; }
.tasks-icons .task-preview-trigger { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; line-clamp:2; overflow:hidden; text-align:center; width:100%; }
.tasks-icons .task-due { margin-top:5px; font-size:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.tasks-icons .task-status-control { width:100%; align-self:center; --task-status-font-size:10px; }
.tasks-icons .task-status { font-size:10px; }
.tasks-icons .task-actions { justify-content:center; align-self:end; gap:4px; width:100%; flex-wrap:nowrap; }
.tasks-icons .task-actions button,.tasks-icons .task-actions a { display:inline-flex; justify-content:center; align-items:center; gap:0; width:30px; height:30px; padding:5px; box-sizing:border-box; font-size:0; border-radius:7px; flex-shrink:0; }
@media(max-width:1100px) { .tasks-list:not(.tasks-grid):not(.tasks-icons) .task-item { grid-template-columns:46px minmax(0,1fr) 160px; }.tasks-list:not(.tasks-grid):not(.tasks-icons) .task-actions { grid-column:2 / -1; } }
@media(max-width:650px) { .tasks-list:not(.tasks-grid):not(.tasks-icons) .task-item { grid-template-columns:40px minmax(0,1fr); padding:16px; }.tasks-list:not(.tasks-grid):not(.tasks-icons) .task-status-control,.tasks-list:not(.tasks-grid):not(.tasks-icons) .task-actions { grid-column:2; }.task-actions { justify-content:flex-start; width:auto; }.tasks-actions { flex-wrap:wrap; }.tasks-search-row { align-items:stretch; }.tasks-search-row > select { flex:1; min-width:0; } }
.task-dialog h2 { font-size: 17px; font-weight: 600; }
.task-dialog label { gap: 6px; font-size: 12px; font-weight: 400; }
.task-dialog input, .task-dialog select, .task-dialog textarea { padding: 8px 10px; font-size: 13px; border-radius: 7px; }
.task-dialog textarea { min-height: 84px; }
.task-dialog .task-field-caption { display: flex; align-items: baseline; gap: 6px; }
.task-dialog .editor-actions button { padding: 8px 12px; font-size: 12px; }
.task-dialog .task-target { font-size: 11px; color: var(--muted); }

.task-preview-art { display:flex; align-items:center; justify-content:center; flex-shrink:0; width:58px; height:58px; border:1px solid var(--border); border-radius:16px; color:var(--accent); background:var(--accent-soft); }
.task-preview > header { align-items:center; gap:14px; background:linear-gradient(120deg,var(--accent-soft),var(--surface) 75%); }
.task-preview h2 { font-size:18px; margin-top:5px; line-height:1.45; }
.task-preview header .icon-button { align-self:flex-start; padding:7px; background:var(--surface); border:1px solid var(--border); border-radius:10px; }
.task-preview-meta { padding:16px; border:1px solid var(--border); border-radius:12px; gap:16px 22px; margin:16px 0 0; }
.task-preview-meta dt { font-size:11px; margin-bottom:7px; }
.task-preview-meta dd { font-size:12px; line-height:1.5; }
.task-folder-link { display:flex; align-items:center; width:100%; gap:12px; padding:14px; text-align:left; border:1px solid var(--border); border-radius:12px; background:var(--surface); }
.task-folder-link:hover { border-color:var(--accent); }
.task-folder-icon { display:flex; padding:10px; color:var(--warning); background:var(--warning-soft); border-radius:10px; flex-shrink:0; }
.task-folder-label { display:grid; gap:5px; min-width:0; flex:1; overflow-wrap:anywhere; }
.task-folder-label small { color:var(--muted); font-size:10px; }
.task-folder-label strong { color:var(--text); font-size:13px; font-weight:500; }
.task-folder-label > span { color:var(--accent); font-size:11px; }
.task-folder-link > svg { flex-shrink:0; color:var(--accent); }
.task-preview-content { padding:16px; margin-top:16px; background:var(--surface-soft); border-radius:12px; }
.task-preview-content h3 { margin:0 0 10px; font-size:12px; font-weight:600; }
.task-preview-description { font-size:13px; line-height:1.75; }
.task-preview footer button { padding:8px 14px; font-size:12px; }
@media(max-width:480px) { .task-preview > header { gap:10px; }.task-preview-art { width:44px; height:44px; border-radius:12px; }.task-preview-art svg { width:25px; height:25px; }.task-preview h2 { font-size:16px; }.task-preview-meta { padding:12px; gap:14px; } }
.task-preview-footer-status { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin-right:auto; font-size:11px; color:var(--muted); }
.task-preview footer { align-items:center; gap:12px; }
</style>
