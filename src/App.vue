<script setup>
import { computed, defineAsyncComponent, onMounted, onBeforeUnmount, ref } from 'vue'
import { FileText, Plus, Search, LogOut, X, Save, RefreshCw, HardDrive, Upload, Download, Files, Image, FileArchive, Music, Video, Folder, FolderPlus, Trash2, ChevronRight, Users, Pencil, List, LayoutGrid, LockKeyhole, UserRound, GitBranch, Mail, Sparkles, ChevronDown, ClipboardList, ClipboardPlus, BookOpen, ClipboardCheck, History } from 'lucide-vue-next'
import AdminPanel from './AdminPanel.vue'
import PasswordChange from './PasswordChange.vue'
import ThemePicker from './ThemePicker.vue'
import BrandLogo from './BrandLogo.vue'
import { Menu } from 'lucide-vue-next'
import { House } from 'lucide-vue-next'
const StartPanel = defineAsyncComponent(() => import('./StartPanel.vue'))
import ImagePreview from './ImagePreview.vue'
import ImageEditor from './ImageEditor.vue'
import FileEmailDialog from './FileEmailDialog.vue'
import FileApproval from './FileApproval.vue'
import ActiveDocuments from './ActiveDocuments.vue'
import FolderTasks from './FolderTasks.vue'
import { resourceTasks } from './resourceTasks.js'
import { apiErrorDetail } from './apiErrors.js'
import DocumentStatusDialog from './DocumentStatusDialog.vue'
import AddDocumentDialog from './AddDocumentDialog.vue'
const TemplatesPanel = defineAsyncComponent(() => import('./TemplatesPanel.vue'))
const DictionariesPanel = defineAsyncComponent(() => import('./DictionariesPanel.vue'))
const AiCommands = defineAsyncComponent(() => import('./AiCommands.vue'))
const ResourceHistory = defineAsyncComponent(() => import('./ResourceHistory.vue'))
const historyTarget = ref(null)
const SurveysPanel = defineAsyncComponent(() => import('./SurveysPanel.vue'))
const SurveyPublic = defineAsyncComponent(() => import('./SurveyPublic.vue'))
const TasksPanel = defineAsyncComponent(() => import('./TasksPanel.vue'))
const DocumentComposer = defineAsyncComponent(() => import('./DocumentComposer.vue'))
const documentComposer = ref(null)
const RichTextEditor = defineAsyncComponent(() => import('./RichTextEditor.vue'))

const statusDocument = ref(null)
async function statusSaved() {
  statusDocument.value = null
  await run(loadDocuments)
}
async function openActiveDocuments() {
  if (busy.value) return
  view.value = 'active'
  await run(loadDocuments)
}
function openDriveFolder(id) {
  if (busy.value) return
  view.value = 'drive'
  navigateFolder(id)
  if (id === null) refreshActivity()
}

const taskTarget = ref(null)
function addResourceTask(item, isFolder = false) {
  if (busy.value || (isFolder && !item.permissions?.read)) return
  taskTarget.value = isFolder ? { folder_id: item.id } : { document_id: item.id }
}

const emailFile = ref(null)
function canViewEmails(file) {
  return !!file.filename && file.user_id === user.value?.id && (file.uploaded_by || file.user_id) === user.value?.id
}
async function emailUpdated() { await run(loadDocuments) }

const imageEditorFile = ref(null)
async function imageSaved() {
  imageEditorFile.value = null
  await run(loadDocuments)
}

const user = ref(null)
const sidebarOpen = ref(false)
const workspaceVisible = computed(() => !!user.value && !user.value.must_change_password && !shareToken && !acceptanceToken && !surveyToken)
const passwordDialog = ref(false)
const accountMenu = ref(false)
const passwordNotice = ref('')
async function passwordSaved(account) {
  user.value = account
  passwordDialog.value = false
  passwordNotice.value = 'Hasło zostało zmienione.'
  await run(loadDocuments)
}
const setupRequired = ref(false)
const connecting = ref(true)
const busy = ref(false)
const error = ref('')
const credentials = ref({ name: '', password: '' })
const documents = ref([])
const taskData = ref({ mine: [], sent: [], waiting: 0 })
const tasksWaiting = computed(() => taskData.value.waiting)
const surveyData = ref([])
const activeSurveys = computed(() => surveyData.value.filter(item => !item.closed_at && item.expected > 0).length)
const templates = ref([])
const search = ref('')
const view = ref('start')
const startSurveyId = ref(null)
const surveyFilter = ref('all')
function startNavigate(target) {
  startSurveyId.value = null
  surveyFilter.value = target === 'surveys' ? 'mine' : 'all'
  view.value = target
  search.value = ''
}
function startOpenSurvey(survey) {
  startSurveyId.value = survey.id
  surveyFilter.value = 'mine'
  view.value = 'surveys'
  search.value = ''
}
const fileLayout = ref('list')
try { if (localStorage.getItem('edokumenty-file-layout') === 'grid') fileLayout.value = 'grid' } catch {}
function changeFileLayout(layout) {
  fileLayout.value = layout
  try { localStorage.setItem('edokumenty-file-layout', layout) } catch {}
}
const fileInput = ref(null)
const addDocumentDialog = ref(false)
function openAddDocument() {
  if (busy.value || !canAddCurrent.value) return
  error.value = ''
  addDocumentDialog.value = true
}
function chooseNewDocument(draft) {
  if (!canAddCurrent.value) return
  editor.value = { ...draft, folder_id: currentFolder.value }
  addDocumentDialog.value = false
}
const uploadProgress = ref('')
const typeFilter = ref('Wszystkie')
const folders = ref([])
const folderAccessIcons = {
  private: { icon: LockKeyhole, label: 'Tylko ja' },
  groups: { icon: Users, label: 'Dostęp dla grup' },
  users: { icon: UserRound, label: 'Dostęp dla wybranych użytkowników' },
  inherit: { icon: GitBranch, label: 'Dostęp dziedziczony' }
}
const folderAccessInfo = folder => folderAccessIcons[folder.access_mode] || folderAccessIcons.inherit
const currentFolder = ref(null)
const folderDialog = ref(false)
const folderName = ref('')
const folderEditing = ref(null)
const folderAccessMode = ref('')
const sharingOptions = ref({ users: [], groups: [] })
const selectedGroupIds = ref([])
const selectedUserIds = ref([])
const sharingRights = ref({ can_add: false, can_delete: false, can_edit: false })
const sharingActions = [{ key: 'can_add', action: 'add', label: 'Dodawanie' }, { key: 'can_delete', action: 'delete', label: 'Usuwanie' }, { key: 'can_edit', action: 'edit', label: 'Edycja' }]
const folderRecipientsValid = computed(() => folderAccessMode.value === 'private' ||
  (folderAccessMode.value === 'groups' && selectedGroupIds.value.length > 0) ||
  (folderAccessMode.value === 'users' && selectedUserIds.value.length > 0))
const rootRights = ref({ read: false, edit: false, add: false, delete: false })
const currentFolderInfo = computed(() => folders.value.find(folder => folder.id === currentFolder.value))
const currentRights = computed(() => currentFolder.value ? currentFolderInfo.value?.permissions || {} : rootRights.value)
const canAddCurrent = computed(() => currentFolder.value ? !!currentFolderInfo.value?.permissions?.add : rootRights.value.add)
const breadcrumbs = computed(() => {
  const path = []
  let folder = currentFolderInfo.value
  while (folder) {
    path.unshift(folder)
    folder = folders.value.find(item => item.id === folder.parent_id)
  }
  return path
})
const filteredFolders = computed(() => folders.value.filter(folder =>
  folder.parent_id === currentFolder.value && typeFilter.value === 'Wszystkie' &&
  folder.name.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
function navigateFolder(id) {
  if (busy.value) return
  currentFolder.value = id
  search.value = ''
  typeFilter.value = 'Wszystkie'
}
async function openNewFolder() {
  if (busy.value) return
  folderEditing.value = null
  folderName.value = ''
  folderAccessMode.value = ''
  selectedGroupIds.value = []
  selectedUserIds.value = []
  sharingRights.value = { can_add: false, can_delete: false, can_edit: false }
  sharingOptions.value = { users: [], groups: [] }
  folderDialog.value = true
  await run(async () => { sharingOptions.value = await api('/sharing-options') })
}
async function createFolder() {
  if (!folderEditing.value && !folderRecipientsValid.value) { error.value = 'Wybierz, kto ma mieć dostęp do folderu.'; return }
  await run(async () => {
    const body = { name: folderName.value, parent_id: currentFolder.value }
    if (!folderEditing.value) {
      body.access_mode = folderAccessMode.value
      body.group_ids = folderAccessMode.value === 'groups' ? selectedGroupIds.value : []
      body.user_ids = folderAccessMode.value === 'users' ? selectedUserIds.value : []
      if (folderAccessMode.value !== 'private') Object.assign(body, sharingRights.value)
    }
    await api(folderEditing.value ? `/folders/${folderEditing.value.id}` : '/folders', folderEditing.value ? 'PATCH' : 'POST', body)
    await loadDocuments()
    folderDialog.value = false
    folderName.value = ''
    folderEditing.value = null
  })
}
async function deleteItem(item, isFolder = false) {
  const name = isFolder ? item.name : item.filename || item.title
  if (busy.value || !window.confirm(`Usunąć ${isFolder ? 'folder' : 'plik'} „${name}”?${isFolder ? ' Folder musi być pusty.' : ' Tej operacji nie można cofnąć.'}`)) return
  await run(async () => {
    await api(isFolder ? `/folders/${item.id}` : `/documents/${item.id}`, 'DELETE')
    await loadDocuments()
  })
}
const editor = ref(null)
const editorTab = ref('document')
const editorTasks = computed(() => resourceTasks(taskData.value, editor.value, 'file'))
const canEditEditor = computed(() => editor.value && (!editor.value.id || editor.value.permissions?.edit))
const statuses = ['Szkic', 'W toku', 'Do podpisania', 'Do modyfikacji', 'Do akceptacji', 'Gotowy', 'Archiwum']
const shared = ref(null)
const shareToken = location.pathname.startsWith('/share/') ? location.pathname.split('/')[2] : null
const acceptanceToken = location.pathname.startsWith('/accept/') ? location.pathname.split('/')[2] : null
const surveyToken = location.pathname.startsWith('/survey/') ? location.pathname.split('/')[2] : null
const files = computed(() => documents.value)
const activeDocuments = computed(() => documents.value.filter(doc => doc.active_actions?.length))
const fileTypes = ['Wszystkie', 'Dokumenty', 'Obrazy', 'Archiwa', 'Audio', 'Wideo', 'Inne']
function fileType(name) {
  if (!name) return 'Dokumenty'
  const extension = name.split('.').pop().toLowerCase()
  if (['pdf', 'doc', 'docx', 'txt', 'rtf', 'xls', 'xlsx', 'csv', 'ppt', 'pptx', 'odt'].includes(extension)) return 'Dokumenty'
  if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'heic', 'bmp', 'avif', 'ico', 'tif', 'tiff'].includes(extension)) return 'Obrazy'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(extension)) return 'Archiwa'
  if (['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(extension)) return 'Audio'
  if (['mp4', 'webm', 'mov', 'avi', 'mkv'].includes(extension)) return 'Wideo'
  return 'Inne'
}
const fileIcons = { Dokumenty: FileText, Obrazy: Image, Archiwa: FileArchive, Audio: Music, Wideo: Video, Inne: Files }
const filteredFiles = computed(() => files.value.filter(doc =>
  doc.folder_id === currentFolder.value &&
  (typeFilter.value === 'Wszystkie' || fileType(doc.filename) === typeFilter.value) &&
  `${doc.filename || ''} ${doc.title}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
function formatSize(bytes) {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} KB`
  return `${(bytes / (1024 * 1024)).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} MB`
}

async function api(path, method = 'GET', body) {
  let response
  try {
    response = await fetch(`/api${path}`, {
      method, credentials: 'same-origin',
      ...(body instanceof FormData ? { body } : body !== undefined ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
    })
  } catch {
    throw new Error('Nie można połączyć się z serwerem. Sprawdź, czy backend jest uruchomiony.')
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = apiErrorDetail(data?.detail)
    const failure = new Error(detail || (response.status >= 500 ? 'Serwer jest niedostępny. Uruchom backend i spróbuj ponownie.' : 'Nie udało się wykonać operacji. Sprawdź wprowadzone dane.'))
    failure.status = response.status
    throw failure
  }
  return data
}

async function run(action) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { await action() } catch (err) { error.value = err.message }
  finally { busy.value = false }
}

async function loadDocuments() {
  if (user.value?.must_change_password) return
  documents.value = await api('/documents')
  templates.value = await api('/templates')
  folders.value = await api('/folders')
  rootRights.value = await api('/access')
  taskData.value = await api('/tasks')
  surveyData.value = await api('/surveys')
  if (currentFolder.value && !folders.value.some(folder => folder.id === currentFolder.value)) currentFolder.value = null
}

async function refreshAccess() {
  await run(async () => {
    const response = await fetch('/api/me')
    if (response.status === 401) {
      user.value = null
      editor.value = null
      folders.value = []
      documents.value = []
      view.value = 'start'
      return
    }
    if (!response.ok) throw new Error('Nie udało się odświeżyć uprawnień.')
    user.value = await response.json()
    await loadDocuments()
  })
}

async function connect() {
  connecting.value = true
  await run(async () => {
    if (acceptanceToken || surveyToken) return
    if (shareToken) {
      shared.value = await api(`/shared/${encodeURIComponent(shareToken)}`)
      return
    }
    const setup = await api('/setup')
    setupRequired.value = setup.required
    if (!setup.required) {
      const response = await fetch('/api/me')
      if (response.status === 401) { user.value = null; editor.value = null; view.value = 'start'; return }
      if (!response.ok) throw new Error('Nie udało się sprawdzić sesji. Spróbuj ponownie.')
      user.value = await response.json()
      await loadDocuments()
    }
  })
  connecting.value = false
}

async function login() {
  await run(async () => {
    user.value = await api(setupRequired.value ? '/setup' : '/login', 'POST', credentials.value)
    credentials.value.password = ''
    passwordNotice.value = ''
    setupRequired.value = false
    view.value = 'start'
    currentFolder.value = null
    await loadDocuments()
  })
}

async function uploadFiles(selectedFiles) {
  if (busy.value || !selectedFiles.length) return
  if (!canAddCurrent.value) { error.value = 'Brak uprawnienia do dodawania plików w tym miejscu.'; return }
  await run(async () => {
    const failures = []
    const selected = Array.from(selectedFiles)
    for (const [index, file] of selected.entries()) {
      uploadProgress.value = `Przesyłanie ${index + 1} z ${selected.length}: ${file.name}`
      try {
        if (file.size > 10 * 1024 * 1024) throw new Error('Maksymalny rozmiar pliku to 10 MB.')
        const form = new FormData()
        form.append('file', file)
        if (currentFolder.value) form.append('folder_id', currentFolder.value)
        await api('/files', 'POST', form)
      } catch (err) { failures.push(`${file.name}: ${err.message}`) }
    }
    try { await loadDocuments() }
    finally {
      uploadProgress.value = ''
      if (fileInput.value) fileInput.value.value = ''
    }
    if (failures.length) throw new Error(failures.join(' '))
  })
}

async function openDocument(doc) {
  await run(async () => {
    const [opened, tasks] = await Promise.all([api(`/documents/${doc.id}`), api('/tasks')])
    editorTab.value = 'document'; editor.value = opened; taskData.value = tasks
  })
}

async function templateDocumentCreated(doc) {
  await run(async () => { await loadDocuments(); view.value = 'active'; editorTab.value = 'document'; editor.value = doc })
}

async function saveDocument() {
  await run(async () => {
    const doc = editor.value
    await documentComposer.value?.flushMemory()
    await api(doc.id ? `/documents/${doc.id}` : '/documents', doc.id ? 'PUT' : 'POST', {
      title: doc.title, category: doc.category, content: doc.content, rich_content: doc.rich_content, field_source: doc.field_source, field_values: doc.field_values || {}, status: doc.status, version: doc.version, ...(!doc.id ? { folder_id: doc.folder_id ?? null } : {})
    })
    await loadDocuments()
    editor.value = null
  })
}

async function logout() {
  await run(async () => {
    await api('/logout', 'POST')
    user.value = null
    passwordDialog.value = false
    accountMenu.value = false
    passwordNotice.value = ''
    documents.value = []
    templates.value = []
    editor.value = null
    addDocumentDialog.value = false
    folders.value = []
    currentFolder.value = null
    folderDialog.value = false
    taskTarget.value = null
    historyTarget.value = null
    emailFile.value = null
    imageEditorFile.value = null
    statusDocument.value = null
    taskData.value = { mine: [], sent: [], waiting: 0 }
    surveyData.value = []
  })
}

const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium' }).format(new Date(value))
let activityTimer, activityRefreshing = false, disposed = false
function canRefreshActivity() {
  return !disposed && user.value && !user.value.must_change_password && !busy.value && !connecting.value && !document.hidden &&
    ['start', 'drive', 'active'].includes(view.value) && !editor.value && !taskTarget.value && !emailFile.value && !imageEditorFile.value && !statusDocument.value && !folderDialog.value && !addDocumentDialog.value
}
async function refreshActivity() {
  if (activityRefreshing || !canRefreshActivity()) return
  activityRefreshing = true
  const accountId = user.value.id, previousDocuments = documents.value
  try {
    const [updated, inbox] = await Promise.all([api('/documents'), api('/tasks')])
    if (canRefreshActivity() && user.value.id === accountId && documents.value === previousDocuments) { documents.value = updated; taskData.value = inbox }
  } catch (err) {
    if (err.status === 401 && canRefreshActivity() && user.value.id === accountId) await connect()
  } finally { activityRefreshing = false }
}
let surveysRefreshing = false
async function refreshSurveyCount() {
  if (surveysRefreshing || disposed || !user.value || user.value.must_change_password || busy.value || connecting.value || document.hidden || view.value === 'surveys') return
  surveysRefreshing = true
  const accountId = user.value.id
  try {
    const data = await api('/surveys')
    if (!disposed && user.value?.id === accountId) surveyData.value = data
  } catch {} finally { surveysRefreshing = false }
}
function refreshWorkspace() { refreshActivity(); refreshSurveyCount() }
onMounted(() => {
  connect()
  activityTimer = setInterval(refreshWorkspace, 15000)
  window.addEventListener('focus', refreshWorkspace)
  document.addEventListener('visibilitychange', refreshWorkspace)
})
onBeforeUnmount(() => {
  disposed = true
  clearInterval(activityTimer)
  window.removeEventListener('focus', refreshWorkspace)
  document.removeEventListener('visibilitychange', refreshWorkspace)
})
</script>

<template>
  <div class="app-shell" :class="{ 'has-workspace': workspaceVisible }" @keydown.esc="sidebarOpen = false">
    <header class="topbar">
      <div class="brand-area"><button v-if="workspaceVisible" class="icon-button sidebar-toggle" :aria-expanded="sidebarOpen" aria-controls="workspace-menu" :aria-label="sidebarOpen ? 'Zamknij menu' : 'Otwórz menu'" @click="sidebarOpen = !sidebarOpen"><Menu :size="22" /></button><a class="brand-link" href="/" aria-label="Space & Flow ? strona g??wna"><BrandLogo /></a></div>
      <div v-if="user" class="account"><ThemePicker /><div class="account-menu"><button :disabled="busy" :aria-expanded="accountMenu" aria-controls="account-actions" @click="accountMenu = !accountMenu"><UserRound :size="18" /> {{ user.name }} <ChevronDown :size="16" /></button><div v-if="accountMenu" id="account-actions" class="account-actions"><button @click="passwordDialog = true; accountMenu = false"><LockKeyhole :size="17" /> Zmień hasło</button></div></div><button class="icon-button" aria-label="Wyloguj" :disabled="busy" @click="logout"><LogOut :size="19" /></button></div>
      <span v-else class="tagline">Twoja przestrzeń dokumentów</span>
    </header>

    <button v-if="workspaceVisible && sidebarOpen" class="sidebar-backdrop" aria-label="Zamknij menu" @click="sidebarOpen = false"></button>
    <div class="app-layout" :class="{ 'with-sidebar': workspaceVisible }">
        <nav v-if="workspaceVisible" id="workspace-menu" class="workspace-sidebar" :class="{ open: sidebarOpen }" @click="sidebarOpen = false" aria-label="Przestrzeń robocza">
          <div class="sidebar-heading"><span class="eyebrow">Menu</span><button class="icon-button sidebar-close" aria-label="Zamknij menu" @click="sidebarOpen = false"><X :size="20" /></button></div>
          <button :class="{ active: view === 'start' }" :aria-current="(view === 'start') ? 'page' : undefined" @click="view = 'start'; search = ''"><House :size="18" /> Start</button>
          <button :class="{ active: view === 'ai' }" :aria-current="(view === 'ai') ? 'page' : undefined" @click="view = 'ai'; search = ''"><Mail :size="18" /> Wiadomości</button>
          <button :class="{ active: view === 'tasks' }" :aria-current="(view === 'tasks') ? 'page' : undefined" @click="view = 'tasks'; search = ''"><ClipboardList :size="18" /> Zadania <span v-if="tasksWaiting">({{ tasksWaiting }})</span></button>
          <button :class="{ active: view === 'surveys' }" :aria-current="(view === 'surveys') ? 'page' : undefined" @click="startSurveyId = null; surveyFilter = 'all'; view = 'surveys'; search = ''"><ClipboardCheck :size="18" /> Ankiety ({{ activeSurveys }})</button>
          <button :class="{ active: view === 'drive' || view === 'active' }" :aria-current="(view === 'drive' || view === 'active') ? 'page' : undefined" @click="openDriveFolder(null)"><HardDrive :size="18" /> Mój dysk</button>
          <button :class="{ active: view === 'templates' }" :aria-current="(view === 'templates') ? 'page' : undefined" @click="view = 'templates'; search = ''"><FileText :size="18" /> Szablony</button>
          <button :class="{ active: view === 'dictionaries' }" :aria-current="(view === 'dictionaries') ? 'page' : undefined" @click="view = 'dictionaries'; search = ''"><BookOpen :size="18" /> Słowniki</button>
          <button v-if="user.role === 'admin'" :class="{ active: view === 'admin' }" :aria-current="(view === 'admin') ? 'page' : undefined" @click="view = 'admin'"><Users :size="18" /> Użytkownicy i grupy</button>
        </nav>
    <main id="workspace-content">
      <div v-if="error" class="error" role="alert"><span>{{ error }}</span><button :disabled="busy" @click="connect"><RefreshCw :size="16" /> Spróbuj ponownie</button></div>
      <p v-if="passwordNotice && user" class="success" role="status">{{ passwordNotice }}</p>
      <p v-if="connecting" class="loading" role="status">Łączenie z serwerem…</p>

      <FileApproval v-else-if="acceptanceToken" :token="acceptanceToken" :api="api" />
      <SurveyPublic v-else-if="surveyToken" :token="surveyToken" :api="api" />
      <article v-else-if="shared" class="shared-document panel">
        <span class="eyebrow">Udostępniony dokument · {{ shared.category }}</span>
        <h1>{{ shared.title }}</h1><RichTextEditor :model-value="shared.rich_content" :plain-text="shared.content" :editable="false" />
        <a v-if="shared.filename" :href="`/api/shared/${encodeURIComponent(shareToken)}/file`">Pobierz: {{ shared.filename }}</a>
      </article>

      <section v-else-if="!user && !shareToken" class="auth panel">
        <span class="eyebrow">Wszystko w jednym miejscu</span>
        <h1>{{ setupRequired ? 'Utwórz pierwsze konto' : 'Witaj w eDokumentach' }}</h1>
        <p class="muted">{{ setupRequired ? 'Skonfiguruj konto, aby rozpocząć pracę z dokumentami.' : 'Zaloguj się, aby otworzyć swoje dokumenty.' }}</p>
        <form @submit.prevent="login">
          <label>Nazwa użytkownika<input v-model="credentials.name" required minlength="2" maxlength="80" autocomplete="username" /></label>
          <label>Hasło<input v-model="credentials.password" type="password" required minlength="10" maxlength="200" :autocomplete="setupRequired ? 'new-password' : 'current-password'" /></label>
          <small class="muted">Hasło musi mieć co najmniej 10 znaków.</small>
          <button class="primary" :disabled="busy" type="submit">{{ busy ? 'Proszę czekać…' : setupRequired ? 'Utwórz konto' : 'Zaloguj się' }}</button>
        </form>
      </section>

      <PasswordChange v-else-if="user?.must_change_password" :api="api" required @saved="passwordSaved" />
      <template v-else-if="user">

        <StartPanel v-if="view === 'start'" :user="user" :surveys="surveyData" :task-data="taskData" :busy="busy" @navigate="startNavigate" @survey="startOpenSurvey" @refresh="run(loadDocuments)" />
        <template v-else-if="view === 'drive'">
          <nav class="breadcrumbs" aria-label="Ścieżka folderu"><button :disabled="busy" @click="navigateFolder(null)"><HardDrive :size="16" /> Mój dysk</button><template v-for="folder in breadcrumbs" :key="folder.id"><ChevronRight :size="15" /><button :disabled="busy" :aria-current="folder.id === currentFolder ? 'page' : undefined" @click="navigateFolder(folder.id)">{{ folder.name }}</button></template><button v-if="currentFolderInfo?.permissions?.read" class="icon-button" :disabled="busy" title="Historia katalogu" aria-label="Historia katalogu" @click="historyTarget = { ...currentFolderInfo, kind: 'folder' }"><History :size="17" /></button></nav>
          <input ref="fileInput" class="file-picker" type="file" multiple aria-label="Wybierz pliki do przesłania" :disabled="busy" @change="uploadFiles($event.target.files)" />
          <p v-if="uploadProgress" class="muted" role="status">{{ uploadProgress }}</p>
          <section class="toolbar drive-toolbar"><div class="search"><Search :size="18" /><input v-model="search" placeholder="Szukaj pliku…" aria-label="Szukaj pliku" /></div><div class="toolbar-controls"><select v-model="typeFilter" aria-label="Filtruj typ pliku"><option v-for="type in fileTypes" :key="type">{{ type }}</option></select><div class="layout-switch" role="group" aria-label="Widok plików"><button :aria-pressed="fileLayout === 'list'" title="Lista" aria-label="Widok listy" @click="changeFileLayout('list')"><List :size="19" /></button><button :aria-pressed="fileLayout === 'grid'" title="Kafelki" aria-label="Widok kafelków" @click="changeFileLayout('grid')"><LayoutGrid :size="19" /></button></div><div v-if="canAddCurrent" class="drive-actions"><button :disabled="busy" @click="openNewFolder"><FolderPlus :size="18" /> Nowy folder</button><button :disabled="busy" @click="fileInput.click()"><Upload :size="18" /> Prześlij pliki</button><button class="primary" :disabled="busy" @click="openAddDocument"><Plus :size="18" /> Dodaj plik</button></div></div></section>
          <section class="panel drive-list" :class="{ 'drive-grid': fileLayout === 'grid' }" aria-label="Pliki na dysku">
            <div v-if="fileLayout === 'list'" class="drive-row drive-heading"><span>Nazwa</span><span>Rozmiar</span><span>Ostatnia zmiana</span><span>Akcje</span></div>
            <button v-if="!currentFolder" class="drive-row active-documents-tile" :disabled="busy" :aria-label="`Aktywne dokumenty: ${activeDocuments.length} wymagających działania. Otwórz listę.`" @click="openActiveDocuments">
              <span class="document-title"><span class="file-icon active-documents-icon"><Sparkles :size="22" aria-hidden="true" /></span><span><strong>Aktywne dokumenty</strong><small>Podpisy, modyfikacje i akceptacje</small></span></span>
              <span class="file-size"><span class="active-documents-count">{{ activeDocuments.length }}</span></span><span class="muted date">Wymagają działania</span>
              <span class="file-actions"><span class="active-documents-arrow"><ChevronRight :size="19" /></span></span>
            </button>
            <div v-for="folder in filteredFolders" :key="folder.id" class="drive-row">
              <button class="folder-open document-title" :disabled="busy" @click="navigateFolder(folder.id)"><span class="file-icon folder-icon"><Folder :size="22" /></span><span><span class="folder-label"><strong>{{ folder.name }}</strong><span class="folder-access-badge" :class="folder.access_mode" :title="folderAccessInfo(folder).label" role="img" :aria-label="folderAccessInfo(folder).label"><component :is="folderAccessInfo(folder).icon" :size="14" aria-hidden="true" /></span></span><small>Folder</small></span></button>
              <span class="muted file-size">—</span><span class="muted date">{{ date(folder.created_at) }}</span>
              <div class="file-actions"><button v-if="folder.permissions?.read" class="icon-button" :disabled="busy" title="Historia zmian" :aria-label="`Historia katalogu ${folder.name}`" @click="historyTarget = { ...folder, kind: 'folder' }"><History :size="17" /></button><button v-if="folder.permissions?.read" class="icon-button" title="Dodaj zadanie" :disabled="busy" :aria-label="`Dodaj zadanie do katalogu ${folder.name}`" @click="addResourceTask(folder, true)"><ClipboardPlus :size="18" /></button><button v-if="folder.permissions?.edit" class="icon-button" :disabled="busy" :aria-label="`Zmień nazwę folderu ${folder.name}`" title="Zmień nazwę" @click="folderEditing = folder; folderName = folder.name; error = ''; folderDialog = true"><Pencil :size="17" /></button><button v-if="folder.permissions?.delete" class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń folder ${folder.name}`" title="Usuń pusty folder" @click="deleteItem(folder, true)"><Trash2 :size="18" /></button></div>
            </div>
            <div v-for="file in filteredFiles" :key="file.id" class="drive-row">
              <span class="document-title"><ImagePreview v-if="fileLayout === 'grid' && fileType(file.filename) === 'Obrazy'" :document-id="file.id" :version="file.version" :name="file.filename" /><span v-else class="file-icon" :class="fileType(file.filename)"><component :is="fileIcons[fileType(file.filename)]" :size="22" /></span><span><button class="document-open" :disabled="busy" @click="fileType(file.filename) === 'Obrazy' ? imageEditorFile = file : openDocument(file)"><strong>{{ file.title }}</strong></button><small>{{ fileType(file.filename) }}{{ file.filename && file.title !== file.filename ? ` · ${file.filename}` : '' }}</small><button v-if="file.permissions?.workflow" class="workflow-status" :class="{ 'requires-action': file.active_actions?.length }" :disabled="busy" :aria-label="`Zmień status: ${file.title}`" title="Zmień status dokumentu" @click="statusDocument = file">{{ file.status }}<ChevronDown :size="12" /></button><small v-else-if="file.active_actions?.length" class="workflow-readonly">{{ file.status }}</small><button v-if="file.approvals && Object.values(file.approvals).some(count => count > 0)" class="approval-summary" :class="{ accepted: file.approvals.accepted > 0 }" :disabled="busy" title="Akceptacje obecnej wersji pliku" @click="emailFile = file">Akceptacje: {{ file.approvals.accepted }}<span v-if="file.approvals.waiting"> · oczekuje {{ file.approvals.waiting }}</span><span v-if="file.approvals.failed"> · błędy {{ file.approvals.failed }}</span></button></span></span>
              <span class="muted file-size">{{ formatSize(file.file_size) }}</span><span class="muted date">{{ date(file.updated_at) }}</span>
              <div class="file-actions"><button class="icon-button" :disabled="busy" :aria-label="`Historia zmian: ${file.filename || file.title}`" title="Historia zmian" @click="historyTarget = { ...file, kind: 'document' }"><History :size="17" /></button><button class="icon-button" :disabled="busy" :aria-label="`Dodaj zadanie do pliku ${file.filename || file.title}`" title="Dodaj zadanie" @click="addResourceTask(file)"><ClipboardPlus :size="18" /></button><button v-if="canViewEmails(file)" class="icon-button" :disabled="busy" :aria-label="`Wyślij e-mailem i sprawdź akceptacje: ${file.filename}`" title="Wyślij e-mailem / akceptacje" @click="emailFile = file"><Mail :size="18" /></button><button v-if="fileType(file.filename) === 'Obrazy'" class="icon-button" :disabled="busy" :aria-label="`Obraz i metadane: ${file.filename}`" title="Kadrowanie, rozdzielczość i metadane" @click="imageEditorFile = file"><Image :size="18" /></button><button v-if="file.permissions?.edit && fileType(file.filename) !== 'Obrazy'" class="icon-button" :disabled="busy" :aria-label="`Edytuj opis pliku ${file.filename || file.title}`" :title="file.filename ? 'Edytuj opis' : 'Edytuj dokument'" @click="openDocument(file)"><Pencil :size="17" /></button><a v-if="file.filename" class="download-button" :href="`/api/documents/${file.id}/file`" :aria-label="`Pobierz ${file.filename}`" title="Pobierz plik"><Download :size="19" /></a><button v-if="file.permissions?.delete" class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń plik ${file.filename || file.title}`" title="Usuń plik" @click="deleteItem(file)"><Trash2 :size="18" /></button></div>
            </div>
            <div v-if="!filteredFiles.length && !filteredFolders.length" class="empty"><Folder :size="39" /><h2>{{ search || typeFilter !== 'Wszystkie' ? 'Brak wyników' : currentFolder ? 'Ten folder jest pusty' : 'Twój dysk jest gotowy' }}</h2><p class="muted">{{ search || typeFilter !== 'Wszystkie' ? 'Zmień wyszukiwanie lub typ pliku.' : canAddCurrent ? 'Dodaj pliki lub utwórz folder, aby je uporządkować.' : 'Brak dostępnych plików. Dostęp do folderów nadaje administrator.' }}</p><button v-if="canAddCurrent" class="primary" :disabled="busy" @click="openAddDocument"><Plus :size="17" /> Dodaj plik</button></div>
          </section>
          <FolderTasks v-if="currentFolderInfo" :folder="currentFolderInfo" :task-data="taskData" :busy="busy" @add-task="addResourceTask($event, true)" @open-tasks="view = 'tasks'; search = ''" />
        </template>
        <ActiveDocuments v-else-if="view === 'active'" :documents="activeDocuments" :folders="folders" :busy="busy" @back="openDriveFolder(null)" @refresh="run(loadDocuments)" @open-document="openDocument" @open-image="imageEditorFile = $event" @open-email="emailFile = $event" @change-status="statusDocument = $event" @open-folder="openDriveFolder" />
        <AiCommands v-else-if="view === 'ai'" :api="api" />
        <SurveysPanel v-else-if="view === 'surveys'" :api="api" :initial-survey-id="startSurveyId" :initial-filter="surveyFilter" @loaded="surveyData = $event" />
        <DictionariesPanel v-else-if="view === 'dictionaries'" :api="api" />
        <TasksPanel v-else-if="view === 'tasks'" :api="api" :current-user="user" :documents="documents" :folders="folders" @open-folder="openDriveFolder" @loaded="taskData = $event" @updated="run(loadDocuments)" @open-document="openDocument" @open-email="emailFile = $event" />
        <template v-else-if="view === 'admin' && user.role === 'admin'"><AdminPanel :api="api" :current-user="user" @updated="refreshAccess" /></template>
        <TemplatesPanel v-else @history="historyTarget = { ...$event, kind: 'template' }" :templates="templates" :api="api" :can-add="rootRights.add" @updated="run(loadDocuments)" @created-document="templateDocumentCreated" />
      </template>
    </main>
    </div>

    <div v-if="passwordDialog && user && !user.must_change_password" class="modal-backdrop"><PasswordChange :api="api" @close="passwordDialog = false" @saved="passwordSaved" /></div>
    <ResourceHistory v-if="historyTarget && user" :resource="historyTarget" :api="api" @close="historyTarget = null" />
    <AddDocumentDialog v-if="addDocumentDialog && user" :templates="templates" :api="api" :folder-id="currentFolder" :folder-name="currentFolderInfo?.name" @close="addDocumentDialog = false" @choose="chooseNewDocument" />
    <DocumentStatusDialog v-if="statusDocument && user" :document="statusDocument" :api="api" @close="statusDocument = null" @saved="statusSaved" />
    <TasksPanel v-if="taskTarget && user" dialog-only :initial-target="taskTarget" :api="api" :current-user="user" :documents="documents" :folders="folders" @close="taskTarget = null" @updated="run(loadDocuments)" />
    <FileEmailDialog v-if="emailFile && user" :file="emailFile" :api="api" @close="emailFile = null" @updated="emailUpdated" />
    <ImageEditor :task-data="taskData" v-if="imageEditorFile && user" :file="imageEditorFile" :api="api" @close="imageEditorFile = null" @saved="imageSaved" />
    <div v-if="folderDialog" class="modal-backdrop">
      <section class="panel folder-dialog" role="dialog" aria-modal="true" aria-labelledby="folder-dialog-title">
        <div class="editor-heading"><h2 id="folder-dialog-title">{{ folderEditing ? 'Zmień nazwę folderu' : 'Nowy folder' }}</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="folderDialog = false"><X :size="21" /></button></div>
        <p class="muted">W: {{ currentFolderInfo?.name || 'Mój dysk' }}</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <form @submit.prevent="createFolder">
          <label>Nazwa folderu<input v-model="folderName" :disabled="busy" required maxlength="120" /></label>
          <template v-if="!folderEditing">
            <fieldset><legend>Kto ma dostęp?</legend><div class="access-modes">
              <label class="check-label"><input v-model="folderAccessMode" type="radio" name="folder-access" value="private" required :disabled="busy" /> Tylko ja</label>
              <label class="check-label"><input v-model="folderAccessMode" type="radio" name="folder-access" value="groups" required :disabled="busy" /> Grupa</label>
              <label class="check-label"><input v-model="folderAccessMode" type="radio" name="folder-access" value="users" required :disabled="busy" /> Użytkownicy</label>
            </div></fieldset>
            <div v-if="folderAccessMode === 'groups'" class="recipient-list" aria-label="Wybierz grupy"><label v-for="group in sharingOptions.groups" :key="group.id" class="check-label"><input v-model="selectedGroupIds" type="checkbox" :value="group.id" :disabled="busy" /> {{ group.name }}</label><p v-if="!sharingOptions.groups.length" class="muted">Brak grup. Grupy tworzy administrator.</p></div>
            <div v-if="folderAccessMode === 'users'" class="recipient-list" aria-label="Wybierz użytkowników"><label v-for="account in sharingOptions.users" :key="account.id" class="check-label"><input v-model="selectedUserIds" type="checkbox" :value="account.id" :disabled="busy" /> {{ account.name }}</label><p v-if="!sharingOptions.users.length" class="muted">Brak innych aktywnych użytkowników.</p></div>
            <template v-if="folderAccessMode === 'groups' || folderAccessMode === 'users'">
              <fieldset><legend>Uprawnienia wybranych odbiorców</legend><div class="permission-checks"><label v-for="right in sharingActions" :key="right.key" class="check-label"><input v-model="sharingRights[right.key]" type="checkbox" :disabled="busy || (user.role !== 'admin' && !currentRights[right.action])" /> {{ right.label }}</label></div></fieldset>
              <p class="muted">Odczyt jest zawsze dostępny. Uprawnienia obejmują podfoldery dziedziczące dostęp. Dokument może edytować tylko jego twórca, a plik usunąć osoba, która go dodała.</p>
            </template>
            <p v-else-if="folderAccessMode === 'private'" class="muted">Dostęp tylko dla Ciebie. Folder nie dziedziczy dostępu z dysku ani folderu nadrzędnego.</p>
          </template>
          <div class="editor-actions"><button type="button" :disabled="busy" @click="folderDialog = false">Anuluj</button><button type="submit" class="primary" :disabled="busy || !folderName.trim() || (!folderEditing && !folderRecipientsValid)"><FolderPlus :size="17" /> {{ folderEditing ? 'Zapisz nazwę' : 'Utwórz folder' }}</button></div>
        </form>
      </section>
    </div>
    <div v-if="editor" class="modal-backdrop">
      <section class="editor panel document-editor" role="dialog" aria-modal="true" aria-labelledby="editor-title">
        <div class="editor-heading"><h2 id="editor-title">{{ editor.id ? 'Edytuj dokument' : 'Nowy dokument' }}</h2><button v-if="editor.id" class="icon-button" :disabled="busy" title="Historia zmian" aria-label="Historia dokumentu" @click="historyTarget = { ...editor, kind: 'document' }"><History :size="18" /></button><button class="icon-button" :disabled="busy" aria-label="Zamknij edytor" @click="editor = null"><X :size="21" /></button></div>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <nav v-if="editorTasks.length" class="document-tabs" aria-label="Widok dokumentu"><button :aria-pressed="editorTab === 'document'" :disabled="busy" @click="editorTab = 'document'"><FileText :size="16" /> Dokument</button><button :aria-pressed="editorTab === 'tasks'" :disabled="busy" @click="editorTab = 'tasks'"><ClipboardList :size="16" /> Zadania <span>{{ editorTasks.length }}</span></button></nav>
        <div v-show="editorTab === 'tasks' && editorTasks.length" class="document-task-content"><FolderTasks embedded :document="editor" :task-data="taskData" :busy="busy" /></div>
        <form v-show="editorTab !== 'tasks' || !editorTasks.length" @submit.prevent="saveDocument">
          <div class="document-metadata">
          <p v-if="!canEditEditor" class="muted">Masz dostęp tylko do odczytu tego dokumentu.</p>
          <label>Tytuł<input v-model="editor.title" :readonly="!canEditEditor" required maxlength="200" /></label>
          <div class="form-grid"><label>Kategoria<input v-model="editor.category" :readonly="!canEditEditor" maxlength="60" /></label><label>Status<select v-model="editor.status" :disabled="!canEditEditor"><option v-for="item in statuses" :key="item">{{ item }}</option></select></label></div>
          </div>
          <DocumentComposer ref="documentComposer" :key="editor.id || 'new'" v-model="editor.rich_content" v-model:plain-text="editor.content" v-model:field-source="editor.field_source" v-model:field-values="editor.field_values" :editable="!!canEditEditor && !busy" :api="api" :title="editor.title" :document-id="editor.id" />
          <div class="editor-actions"><button type="button" :disabled="busy" @click="editor = null">Zamknij</button><button v-if="canEditEditor" class="primary" :disabled="busy" type="submit"><Save :size="17" /> {{ busy ? 'Zapisywanie…' : 'Zapisz dokument' }}</button></div>
        </form>
      </section>
    </div>
  </div>
</template>
