<script setup>
import { computed, defineAsyncComponent, onMounted, onBeforeUnmount, ref } from 'vue'
import { FileText, Plus, Search, LogOut, X, Save, RefreshCw, HardDrive, Upload, Download, Files, Image, FileArchive, Music, Video, Folder, FolderPlus, Trash2, ChevronRight, Users, Pencil, List, LayoutGrid, Grid3X3, LockKeyhole, UserRound, GitBranch, Mail, Sparkles, ChevronDown, ClipboardList, ClipboardPlus, BookOpen, ClipboardCheck, History } from 'lucide-vue-next'
import AdminPanel from './AdminPanel.vue'
import PasswordChange from './PasswordChange.vue'
const ProductLanding = defineAsyncComponent(() => import('./ProductLanding.vue'))
const PwaSettings = defineAsyncComponent(() => import('./PwaSettings.vue'))
const pwaDialog = ref(false)
import ThemePicker from './ThemePicker.vue'
import BrandLogo from './BrandLogo.vue'
import WorkspaceMenu from './WorkspaceMenu.vue'
import { Menu, House, CalendarDays, StickyNote, Eye, Settings } from 'lucide-vue-next'
const StartPanel = defineAsyncComponent(() => import('./StartPanel.vue'))
const ClientMail = defineAsyncComponent(() => import('./ClientMail.vue'))
const MailSettings = defineAsyncComponent(() => import('./MailSettings.vue'))
const MailAnalysis = defineAsyncComponent(() => import('./MailAnalysis.vue'))
const EDeliveryPanel = defineAsyncComponent(() => import('./EDeliveryPanel.vue'))
const EDeliverySettings = defineAsyncComponent(() => import('./EDeliverySettings.vue'))
const HelpPanel = defineAsyncComponent(() => import('./HelpPanel.vue'))
const CompaniesPanel = defineAsyncComponent(() => import('./CompaniesPanel.vue'))
const helpTopic = ref('help')
function openHelp(topic = view.value) { helpTopic.value = topic === 'help' ? 'help' : topic; view.value = 'help'; sidebarOpen.value = false }
const NotesPanel = defineAsyncComponent(() => import('./NotesPanel.vue'))
import { ensureDocumentsFolder } from './documentsFolder.js'
const documentsFolderId = ref(null)
const startNoteDraft = ref(null)
const startAssistantPrompt = ref('')
function startNote(draft) { startNoteDraft.value = draft; startNavigate('notes') }
function askForNote() { startAssistantPrompt.value = 'Dodaj notatkę: '; startNavigate('start') }
import ImagePreview from './ImagePreview.vue'
const PdfPreview = defineAsyncComponent(() => import('./PdfPreview.vue'))
import ImageEditor from './ImageEditor.vue'
import FileEmailDialog from './FileEmailDialog.vue'
import FileApproval from './FileApproval.vue'
import ActiveDocuments from './ActiveDocuments.vue'
import FolderTasks from './FolderTasks.vue'
import { resourceTasks } from './resourceTasks.js'
import { apiErrorDetail } from './apiErrors.js'
import DocumentStatusDialog from './DocumentStatusDialog.vue'
import { Share2 } from 'lucide-vue-next'
const ExternalShareDialog = defineAsyncComponent(() => import('./ExternalShareDialog.vue'))
const PublicShare = defineAsyncComponent(() => import('./PublicShare.vue'))
const shareResource = ref(null)
import AddDocumentDialog from './AddDocumentDialog.vue'
const TemplatesPanel = defineAsyncComponent(() => import('./TemplatesPanel.vue'))
const DictionariesPanel = defineAsyncComponent(() => import('./DictionariesPanel.vue'))
const AiCommands = defineAsyncComponent(() => import('./AiCommands.vue'))
const ResourceHistory = defineAsyncComponent(() => import('./ResourceHistory.vue'))
const historyTarget = ref(null)
const SurveysPanel = defineAsyncComponent(() => import('./SurveysPanel.vue'))
const SurveyPublic = defineAsyncComponent(() => import('./SurveyPublic.vue'))
const TasksPanel = defineAsyncComponent(() => import('./TasksPanel.vue'))
const FlowsPanel = defineAsyncComponent(() => import('./FlowsPanel.vue'))
const CalendarPanel = defineAsyncComponent(() => import('./CalendarPanel.vue'))
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
async function enterDocumentsFolder() {
  const result = await ensureDocumentsFolder(api, user.value.id)
  folders.value = result.folders
  documentsFolderId.value = result.folder.id
  currentFolder.value = result.folder.id
  view.value = 'documents'
  search.value = ''
  typeFilter.value = 'Wszystkie'
}
async function openDocumentsFolder() {
  await run(async () => {
    await enterDocumentsFolder()
    await loadDocuments()
  })
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
const pdfPreviewFile = ref(null)
function openFile(file) {
  if (/\.pdf$/i.test(file.filename || '')) { pdfPreviewFile.value = file; return }
  if (fileType(file.filename) === 'Obrazy') { imageEditorFile.value = file; return }
  return openDocument(file)
}
async function imageSaved() {
  imageEditorFile.value = null
  await run(loadDocuments)
}

const user = ref(null)
const sidebarOpen = ref(false)
const workspaceVisible = computed(() => !!user.value && !user.value.must_change_password && !shareToken && !publicShareToken && !acceptanceToken && !surveyToken)
const passwordDialog = ref(false)
const accountMenu = ref(false)
const passwordNotice = ref('')
async function passwordSaved(account) {
  user.value = account
  passwordDialog.value = false
  passwordNotice.value = 'Hasło zostało zmienione.'
  await run(loadDocuments)
  applyInitialSection()
}
const setupRequired = ref(false)
const connecting = ref(true)
const marketingVisible = computed(() => !user.value && !connecting.value && !shareToken && !publicShareToken && !acceptanceToken && !surveyToken)
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
const selectedDictionaryId = ref(null), dictionaryRequest = ref(0), dictionaryRevision = ref(0)
function openDictionary(id) {
  selectedDictionaryId.value = id
  dictionaryRequest.value++
  view.value = 'dictionaries'
  search.value = ''
}
const mailFolder = ref('inbox'), mailFolderRequest = ref(0)
const mailAnalysisDay = ref(''), mailMessageId = ref(null)
const mailDetailOpen = ref(false)
function openMailFolder(folder) {
  if (!['analysis', 'inbox', 'sent', 'drafts', 'spam', 'trash', 'archive'].includes(folder)) return
  mailMessageId.value = null; mailFolder.value = folder; mailFolderRequest.value++
  mailDetailOpen.value = false
  view.value = 'mail'; search.value = ''
}
function openMailAnalysisMessage(message) {
  openMailFolder(message.folder)
  mailDetailOpen.value = true
  mailMessageId.value = message.id
}
const sectionIcons = { flows: GitBranch, 'edelivery-settings': Settings, 'mail-settings': Settings, start: House, mail: Mail, edelivery: Mail, ai: Mail, tasks: ClipboardList, calendar: CalendarDays, notes: StickyNote, documents: Files, surveys: ClipboardCheck, drive: HardDrive, active: ClipboardCheck, templates: FileText, dictionaries: BookOpen, help: BookOpen, companies: Users, admin: Users }

const startAiPrompt = ref('')
function startCommand(prompt) { startAiPrompt.value = prompt; startNavigate('ai') }
async function startDocument(draft) {
  await run(async () => {
    await enterDocumentsFolder()
    if (!canAddCurrent.value) throw new Error('Brak uprawnienia do dodawania dokumentów w katalogu Dokumenty.')
    editorTab.value = 'document'
    editor.value = { ...draft, folder_id: currentFolder.value }
  })
}
async function startScheduled() { startNavigate('calendar'); await run(loadDocuments) }
const startSurveyDraft = ref(null)
function startSurvey(draft) { startSurveyDraft.value = draft; startNavigate('surveys'); surveyFilter.value = 'own' }
const startSurveyId = ref(null)
const surveyFilter = ref('all')
function startNavigate(target) {
  if (target === 'mail') { mailMessageId.value = null; mailDetailOpen.value = false; mailFolder.value = 'inbox'; mailFolderRequest.value++ }
  if (target === 'documents') { openDocumentsFolder(); return }
  startSurveyId.value = null
  surveyFilter.value = target === 'surveys' ? 'mine' : 'all'
  view.value = target
  search.value = ''
}
function menuNavigate(target) {
  if (target === 'pwa') { pwaDialog.value = true; sidebarOpen.value = false; return }
  if (target === 'dictionaries') { openDictionary(null); return }
  if (target === 'help') { openHelp('help'); return }
  if (target === 'drive') { openDriveFolder(null); return }
  if (target === 'surveys') {
    startSurveyId.value = null
    surveyFilter.value = 'all'
    view.value = 'surveys'
    search.value = ''
    return
  }
  startNavigate(target)
}
function startOpenSurvey(survey) {
  startSurveyId.value = survey.id
  surveyFilter.value = 'mine'
  view.value = 'surveys'
  search.value = ''
}
const fileLayout = ref('list')
try {
  const saved = localStorage.getItem('edokumenty-file-layout')
  if (['list', 'grid', 'icons'].includes(saved)) fileLayout.value = saved
} catch {}
function changeFileLayout(layout) {
  if (!['list', 'grid', 'icons'].includes(layout)) return
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
function openUploadPicker() {
  if (busy.value || !canAddCurrent.value) return
  error.value = ''
  addDocumentDialog.value = false
  fileInput.value?.click()
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
const draggedFile = ref(null)
const dropFolder = ref(undefined)
function startFileDrag(event, file) {
  if (busy.value || !file.permissions?.move) { event.preventDefault(); return }
  draggedFile.value = file
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('application/x-edokumenty-document', file.id)
}
function endFileDrag() { draggedFile.value = null; dropFolder.value = undefined }
function canDropFile(folderId) {
  return !busy.value && draggedFile.value && draggedFile.value.folder_id !== folderId &&
    (folderId == null ? rootRights.value.add : folders.value.find(folder => folder.id === folderId)?.permissions?.add)
}
function dragOverFolder(event, folderId) {
  if (!canDropFile(folderId)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dropFolder.value = folderId
}
async function dropFile(event, folderId) {
  if (!canDropFile(folderId)) return
  event.preventDefault()
  const file = draggedFile.value
  endFileDrag()
  await run(async () => {
    try { await api(`/documents/${file.id}/move`, 'PATCH', { folder_id: folderId, version: file.version }) }
    finally { await loadDocuments() }
  })
}

const folderDownloadProgress = ref('')
async function downloadFolder(folder) {
  await run(async () => {
    folderDownloadProgress.value = `Przygotowywanie ZIP katalogu „${folder.name}”…`
    try {
      const response = await fetch(`/api/folders/${encodeURIComponent(folder.id)}/archive`, {
        credentials: 'same-origin', headers: { 'X-Account-ID': user.value.id }
      })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new Error(apiErrorDetail(data?.detail) || 'Nie udało się pobrać katalogu.')
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = folder.name.replace(/[\\/:*?"<>|]/g, '_') + '.zip'
      document.body.append(link); link.click(); link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } finally { folderDownloadProgress.value = '' }
  })
}
async function downloadPdf(doc) {
  await run(async () => {
    if (editor.value === doc && canEditEditor.value) {
      await documentComposer.value?.flushMemory()
      const saved = await api(doc.id ? `/documents/${doc.id}` : '/documents', doc.id ? 'PUT' : 'POST', {
        title: doc.title, category: doc.category, content: doc.content, rich_content: doc.rich_content,
        field_source: doc.field_source, field_values: doc.field_values || {}, status: doc.status,
        version: doc.version, ...(!doc.id ? { folder_id: doc.folder_id ?? null } : {})
      })
      editor.value = saved
      doc = saved
      await loadDocuments()
    }
    const response = await fetch(`/api/documents/${doc.id}/pdf`, {
      credentials: 'same-origin', headers: { 'X-Account-ID': user.value.id }
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      throw new Error(apiErrorDetail(data?.detail) || 'Nie udało się pobrać PDF.')
    }
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = (doc.title || 'Dokument').replace(/[\\/:*?"<>|]/g, '_') + '.pdf'
    document.body.append(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
}
const breadcrumbs = computed(() => {
  const path = []
  let folder = currentFolderInfo.value
  while (folder) {
    path.unshift(folder)
    folder = folders.value.find(item => item.id === folder.parent_id)
  }
  return view.value === 'documents' ? path.filter(folder => folder.id !== documentsFolderId.value) : path
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
  if (busy.value || !canAddCurrent.value) return
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
const publicShareToken = location.pathname.startsWith('/public-share/') ? location.pathname.split('/')[2] : null
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
      headers: { ...(user.value?.id ? { 'X-Account-ID': user.value.id } : {}), ...(!(body instanceof FormData) && body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      ...(body instanceof FormData ? { body } : body !== undefined ? { body: JSON.stringify(body) } : {})
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
  if (currentFolder.value && !folders.value.some(folder => folder.id === currentFolder.value)) {
    currentFolder.value = null
    if (view.value === 'documents') {
      documentsFolderId.value = null
      view.value = 'start'
      error.value = 'Katalog Dokumenty jest już niedostępny. Otwórz sekcję Dokumenty ponownie.'
    }
  }
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
    if (acceptanceToken || surveyToken || publicShareToken) return
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
    startNoteDraft.value = null
    startAssistantPrompt.value = ''
    documentsFolderId.value = null
    view.value = 'start'
    currentFolder.value = null
    await loadDocuments()
    applyInitialSection()
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
    pwaDialog.value = false
    startNoteDraft.value = null
    startAssistantPrompt.value = ''
    documentsFolderId.value = null
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
    pdfPreviewFile.value = null
    statusDocument.value = null
    taskData.value = { mine: [], sent: [], waiting: 0 }
    surveyData.value = []
    if (window.location.hash === '#logowanie') {
      window.history.replaceState(null, '', window.location.pathname + window.location.search)
    }
  })
  if (!user.value) window.scrollTo(0, 0)
}
function reloadWorkspace() { window.location.reload() }
async function returnToAdministrator() {
  await run(async () => { await api('/admin/impersonation/stop', 'POST'); reloadWorkspace() })
}

const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium' }).format(new Date(value))
let activityTimer, activityRefreshing = false, disposed = false
function canRefreshActivity() {
  return !disposed && user.value && !user.value.must_change_password && !busy.value && !connecting.value && !document.hidden &&
    ['start', 'drive', 'active', 'documents'].includes(view.value) && !editor.value && !taskTarget.value && !emailFile.value && !imageEditorFile.value && !pdfPreviewFile.value && !statusDocument.value && !folderDialog.value && !addDocumentDialog.value
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
function applyInitialSection() {
  if (!user.value || user.value.must_change_password || shareToken || publicShareToken || acceptanceToken || surveyToken) return
  const address = new URL(window.location.href)
  const section = address.searchParams.get('section')
  if (!['mail', 'tasks', 'calendar'].includes(section)) return
  startNavigate(section)
  address.searchParams.delete('section')
  window.history.replaceState(null, '', address.pathname + address.search + address.hash)
}
onMounted(() => {
  connect().then(applyInitialSection)
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
  <div class="app-shell" :class="{ 'has-workspace': workspaceVisible, 'product-shell': marketingVisible, 'mail-section': workspaceVisible && view === 'mail' }" @keydown.esc="sidebarOpen = false">
    <header v-if="!marketingVisible" class="topbar">
      <div class="brand-area"><button v-if="workspaceVisible" class="icon-button sidebar-toggle" :aria-expanded="sidebarOpen" aria-controls="workspace-menu" :aria-label="sidebarOpen ? 'Zamknij menu' : 'Otwórz menu'" @click="sidebarOpen = !sidebarOpen"><Menu :size="22" /></button><a class="brand-link" href="/" aria-label="Space & Flow ? strona g??wna"><BrandLogo /></a></div>
      <div v-if="workspaceVisible" class="workspace-heading"><span class="workspace-section-icon"><component :is="sectionIcons[view] || FileText" :size="24" /></span><div id="workspace-title"><div v-if="view === 'start' || view === 'drive'"><h1>{{ view === 'start' ? 'Start' : 'M?j dysk' }}</h1><p>{{ view === 'start' ? 'Twoje zadania, dokumenty i pomys?y w jednym miejscu.' : 'Twoje pliki i katalogi.' }}</p></div></div></div>
      <div v-if="workspaceVisible" id="workspace-search" class="workspace-search"></div>
      <button v-if="workspaceVisible" class="icon-button" title="Pomoc do bieżącego modułu" aria-label="Pomoc do bieżącego modułu" @click="openHelp()"><BookOpen :size="20" /></button>
      <div v-if="user" class="account"><ThemePicker /><div class="account-menu"><button :disabled="busy" :aria-expanded="accountMenu" aria-controls="account-actions" @click="accountMenu = !accountMenu"><UserRound :size="18" /> {{ user.name }} <small v-if="user.company_name" class="account-company">{{ user.company_name }}</small> <ChevronDown :size="16" /></button><div v-if="accountMenu" id="account-actions" class="account-actions"><button v-if="!user.impersonation && !user.must_change_password" @click="pwaDialog = true; accountMenu = false"><Settings :size="17" /> Aplikacja i powiadomienia</button><button v-if="!user.impersonation" @click="passwordDialog = true; accountMenu = false"><LockKeyhole :size="17" /> Zmień hasło</button></div></div><button class="icon-button" aria-label="Wyloguj" :disabled="busy" @click="logout"><LogOut :size="19" /></button></div>
      <span v-else class="tagline">Twoja przestrzeń dokumentów</span>
    </header>

    <button v-if="workspaceVisible && sidebarOpen" class="sidebar-backdrop" aria-label="Zamknij menu" @click="sidebarOpen = false"></button>
    <div class="app-layout" :class="{ 'with-sidebar': workspaceVisible }">
        <WorkspaceMenu v-if="workspaceVisible" :user="user" :api="api" :view="view" :open="sidebarOpen" :tasks-waiting="tasksWaiting" :active-surveys="activeSurveys" :mail-folder="mailFolder" :dictionary-id="selectedDictionaryId" :dictionary-revision="dictionaryRevision" @dictionary="openDictionary" @mail-folder="openMailFolder" @navigate="menuNavigate" @close="sidebarOpen = false" @order-saved="user = { ...user, menu_order: $event }" />
    <main id="workspace-content" :class="{ 'product-content': marketingVisible, 'mail-workspace': view === 'mail' }">
      <aside v-if="user?.impersonation" class="impersonation-banner" role="status"><div><strong>{{ user.impersonation.read_only ? 'Podgląd konta: ' : 'Konto klienta: ' }}{{ user.name }}</strong><span v-if="user.impersonation.read_only">Tylko do odczytu</span><span>{{ user.company_name }} · Administrator: {{ user.impersonation.actor_name }}. {{ user.impersonation.read_only ? 'Podgląd bez możliwości wprowadzania zmian.' : 'Zmiany są rzeczywiste.' }}</span></div><button :disabled="busy" @click="returnToAdministrator">Wróć na konto administratora</button></aside>

      <div v-if="error && !marketingVisible" class="error" role="alert"><span>{{ error }}</span><button :disabled="busy" @click="connect"><RefreshCw :size="16" /> Spróbuj ponownie</button></div>
      <p v-if="passwordNotice && user" class="success" role="status">{{ passwordNotice }}</p>
      <p v-if="connecting" class="loading" role="status">Łączenie z serwerem…</p>

      <FileApproval v-else-if="acceptanceToken" :token="acceptanceToken" :api="api" />
      <SurveyPublic v-else-if="surveyToken" :token="surveyToken" :api="api" />
      <PublicShare v-else-if="publicShareToken" :token="publicShareToken" :api="api" />
      <article v-else-if="shared" class="shared-document panel">
        <span class="eyebrow">Udostępniony dokument · {{ shared.category }}</span>
        <h1>{{ shared.title }}</h1><RichTextEditor :model-value="shared.rich_content" :plain-text="shared.content" :editable="false" />
        <a v-if="shared.filename" :href="`/api/shared/${encodeURIComponent(shareToken)}/file`">Pobierz: {{ shared.filename }}</a>
      </article>

      <ProductLanding v-else-if="!user && !shareToken" :error="error"><section class="auth panel">
        <span class="eyebrow">Wszystko w jednym miejscu</span>
        <h1>{{ setupRequired ? 'Utwórz pierwsze konto' : 'Witaj w eDokumentach' }}</h1>
        <p class="muted">{{ setupRequired ? 'Skonfiguruj konto, aby rozpocząć pracę z dokumentami.' : 'Zaloguj się, aby otworzyć swoje dokumenty.' }}</p>
        <form @submit.prevent="login">
          <label>Nazwa użytkownika<input v-model="credentials.name" required minlength="2" maxlength="80" autocomplete="username" /></label>
          <label>Hasło<input v-model="credentials.password" type="password" required minlength="10" maxlength="200" :autocomplete="setupRequired ? 'new-password' : 'current-password'" /></label>
          <small class="muted">Hasło musi mieć co najmniej 10 znaków.</small>
          <button class="primary" :disabled="busy" type="submit">{{ busy ? 'Proszę czekać…' : setupRequired ? 'Utwórz konto' : 'Zaloguj się' }}</button>
        </form>
      </section></ProductLanding>

      <PasswordChange v-else-if="user?.must_change_password" :api="api" required @saved="passwordSaved" />
      <template v-else-if="user">
        <HelpPanel v-if="view === 'help'" :user="user" :initial-topic="helpTopic" @navigate="menuNavigate" />
        <CompaniesPanel v-else-if="view === 'companies' && user.is_superadmin" :api="api" />
        <StartPanel v-else-if="view === 'start'" :user="user" :surveys="surveyData" :task-data="taskData" :busy="busy" :api="api" :initial-prompt="startAssistantPrompt" @prompt-consumed="startAssistantPrompt = ''" @note="startNote" @document="startDocument" @survey-draft="startSurvey" @scheduled="startScheduled" @navigate="startNavigate" @mail-analysis="openMailFolder('analysis')" @command="startCommand" @survey="startOpenSurvey" @refresh="run(loadDocuments)" />
        <MailAnalysis v-else-if="view === 'mail' && mailFolder === 'analysis'" :api="api" :initial-day="mailAnalysisDay" :request="mailFolderRequest" @day-change="mailAnalysisDay = $event" @open-folder="openMailFolder" @open-message="openMailAnalysisMessage" />
        <ClientMail v-else-if="view === 'mail'" :current-user="user" @task-created="run(loadDocuments)" :key="mailFolder === 'inbox' && !mailDetailOpen ? 'unified' : 'email'" :unified="mailFolder === 'inbox' && !mailDetailOpen" @navigate="menuNavigate" @open-settings="menuNavigate('mail-settings')" :api="api" :initial-folder="mailFolder" :folder-request="mailFolderRequest" :initial-message-id="mailMessageId" @message-opened="mailMessageId = null" @folder-change="mailFolder = $event" />
        <EDeliveryPanel v-else-if="view === 'edelivery'" :api="api" @open-settings="menuNavigate('edelivery-settings')" />
        <EDeliverySettings v-else-if="view === 'edelivery-settings'" :api="api" @close="menuNavigate('edelivery')" />
        <MailSettings v-else-if="view === 'mail-settings'" :api="api" @close="openMailFolder('inbox')" />
        <FlowsPanel v-else-if="view === 'flows'" :api="api" :current-user="user" />
        <NotesPanel v-else-if="view === 'notes'" :api="api" :initial-draft="startNoteDraft" @draft-consumed="startNoteDraft = null" @ai="askForNote" />
        <template v-else-if="view === 'drive' || view === 'documents'">
          <header v-if="view === 'documents'" class="documents-heading">
            <Teleport to="#workspace-title"><div><h1>Dokumenty</h1><p>Dodawaj katalogi i dokumenty w bieżącym katalogu.</p></div></Teleport>
            <p v-if="!canAddCurrent" class="muted">Nie masz uprawnienia do dodawania w tym katalogu.</p>
          </header>
          <nav class="breadcrumbs" aria-label="Ścieżka folderu"><button :class="{ 'folder-drop-target': dropFolder === (view === 'documents' ? documentsFolderId : null) }" @dragover="dragOverFolder($event, view === 'documents' ? documentsFolderId : null)" @dragleave="dropFolder = undefined" @drop.stop="dropFile($event, view === 'documents' ? documentsFolderId : null)" :disabled="busy" :aria-current="view === 'documents' && currentFolder === documentsFolderId ? 'page' : undefined" @click="navigateFolder(view === 'documents' ? documentsFolderId : null)"><Files v-if="view === 'documents'" :size="16" /><HardDrive v-else :size="16" /> {{ view === 'documents' ? '\\Dokumenty' : 'Mój dysk' }}</button><template v-for="folder in breadcrumbs" :key="folder.id"><ChevronRight :size="15" /><button :class="{ 'folder-drop-target': dropFolder === folder.id }" @dragover="dragOverFolder($event, folder.id)" @dragleave="dropFolder = undefined" @drop.stop="dropFile($event, folder.id)" :disabled="busy" :aria-current="folder.id === currentFolder ? 'page' : undefined" @click="navigateFolder(folder.id)">{{ folder.name }}</button></template><button v-if="currentFolderInfo?.permissions?.read" class="icon-button" :disabled="busy" title="Historia katalogu" aria-label="Historia katalogu" @click="historyTarget = { ...currentFolderInfo, kind: 'folder' }"><History :size="17" /></button><button v-if="currentFolderInfo?.permissions?.read" :disabled="busy" title="Pobierz katalog z podkatalogami jako ZIP" aria-label="Pobierz bieżący katalog jako ZIP" @click="downloadFolder(currentFolderInfo)"><Download :size="17" /> Pobierz katalog ZIP</button><button v-if="currentFolderInfo?.can_share" :disabled="busy" aria-label="Udostępnij bieżący katalog przez link" @click="shareResource = { ...currentFolderInfo, kind: 'folder' }"><Share2 :size="17" /> Udostępnij</button></nav>
          <input ref="fileInput" class="file-picker" type="file" multiple aria-label="Wybierz pliki do przesłania" :disabled="busy" @change="uploadFiles($event.target.files)" />
          <p v-if="folderDownloadProgress" class="muted" role="status">{{ folderDownloadProgress }}</p>
          <p v-if="uploadProgress" class="muted" role="status">{{ uploadProgress }}</p>
          <section class="toolbar drive-toolbar page-menu"><Teleport to="#workspace-search"><div class="search"><Search :size="18" /><input v-model="search" placeholder="Szukaj pliku…" aria-label="Szukaj pliku" /></div></Teleport><div class="toolbar-controls"><select v-model="typeFilter" aria-label="Filtruj typ pliku"><option v-for="type in fileTypes" :key="type">{{ type }}</option></select><div class="layout-switch" role="group" aria-label="Widok plików"><button :aria-pressed="fileLayout === 'list'" title="Lista" aria-label="Widok listy" @click="changeFileLayout('list')"><List :size="18" /> Lista</button><button :aria-pressed="fileLayout === 'grid'" title="Kafelki" aria-label="Widok kafelków" @click="changeFileLayout('grid')"><LayoutGrid :size="18" /> Kafelki</button><button :aria-pressed="fileLayout === 'icons'" title="Ikony" aria-label="Widok ikon" @click="changeFileLayout('icons')"><Grid3X3 :size="18" /> Ikony</button></div><div v-if="canAddCurrent || view === 'documents'" class="drive-actions"><button :disabled="busy || !canAddCurrent" @click="openNewFolder"><FolderPlus :size="18" /> Dodaj katalog</button><button :disabled="busy || !canAddCurrent" @click="openUploadPicker"><Upload :size="18" /> Prześlij pliki</button><button class="primary" :disabled="busy || !canAddCurrent" @click="openAddDocument"><Plus :size="18" /> Dodaj dokument</button></div></div></section>
          <section class="panel drive-list" :class="{ 'drive-grid': fileLayout === 'grid', 'drive-icons': fileLayout === 'icons' }" aria-label="Pliki na dysku">
            <div v-if="fileLayout === 'list'" class="drive-row drive-heading"><span>Nazwa</span><span>Rozmiar</span><span>Ostatnia zmiana</span><span>Akcje</span></div>
            <button v-if="view === 'documents' && currentFolder === documentsFolderId" class="drive-row active-documents-tile" :disabled="busy" :aria-label="`Aktywne dokumenty: ${activeDocuments.length} wymagających działania. Otwórz listę.`" @click="openActiveDocuments">
              <span class="document-title"><span class="file-icon active-documents-icon"><Sparkles :size="22" aria-hidden="true" /></span><span><strong>Aktywne dokumenty</strong><small>Podpisy, modyfikacje i akceptacje</small></span></span>
              <span class="file-size"><span class="active-documents-count">{{ activeDocuments.length }}</span></span><span class="muted date">Wymagają działania</span>
              <span class="file-actions"><span class="active-documents-arrow"><ChevronRight :size="19" /></span></span>
            </button>
            <div v-for="folder in filteredFolders" :key="folder.id" class="drive-row" :class="{ 'folder-drop-target': dropFolder === folder.id }" @dragover="dragOverFolder($event, folder.id)" @dragleave="dropFolder = undefined" @drop.stop="dropFile($event, folder.id)">
              <button class="folder-open document-title" :disabled="busy" @click="navigateFolder(folder.id)"><span class="file-icon folder-icon"><Folder :size="22" /></span><span><span class="folder-label"><strong>{{ folder.name }}</strong><span class="folder-access-badge" :class="folder.access_mode" :title="folderAccessInfo(folder).label" role="img" :aria-label="folderAccessInfo(folder).label"><component :is="folderAccessInfo(folder).icon" :size="14" aria-hidden="true" /></span></span><small>Folder</small></span></button>
              <span class="muted file-size">—</span><span class="muted date">{{ date(folder.created_at) }}</span>
              <div class="file-actions"><button v-if="folder.can_share" class="icon-button" :disabled="busy" title="Udostępnij przez link zewnętrzny" :aria-label="`Udostępnij katalog ${folder.name}`" @click="shareResource = { ...folder, kind: 'folder' }"><Share2 :size="18" /></button><button v-if="folder.permissions?.read" class="icon-button" :disabled="busy" title="Pobierz katalog jako ZIP" :aria-label="`Pobierz katalog ${folder.name} jako ZIP`" @click="downloadFolder(folder)"><Download :size="18" /></button><button v-if="folder.permissions?.read" class="icon-button" :disabled="busy" title="Historia zmian" :aria-label="`Historia katalogu ${folder.name}`" @click="historyTarget = { ...folder, kind: 'folder' }"><History :size="17" /></button><button v-if="folder.permissions?.read" class="icon-button" title="Dodaj zadanie" :disabled="busy" :aria-label="`Dodaj zadanie do katalogu ${folder.name}`" @click="addResourceTask(folder, true)"><ClipboardPlus :size="18" /></button><button v-if="folder.permissions?.edit" class="icon-button" :disabled="busy" :aria-label="`Zmień nazwę folderu ${folder.name}`" title="Zmień nazwę" @click="folderEditing = folder; folderName = folder.name; error = ''; folderDialog = true"><Pencil :size="17" /></button><button v-if="folder.permissions?.delete" class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń folder ${folder.name}`" title="Usuń pusty folder" @click="deleteItem(folder, true)"><Trash2 :size="18" /></button></div>
            </div>
            <div v-for="file in filteredFiles" :key="file.id" class="drive-row" :class="{ 'file-dragging': draggedFile?.id === file.id }" :draggable="!busy && !!file.permissions?.move" @dragstart="startFileDrag($event, file)" @dragend="endFileDrag">
              <span class="document-title"><ImagePreview v-if="fileLayout === 'grid' && fileType(file.filename) === 'Obrazy'" :document-id="file.id" :version="file.version" :name="file.filename" /><span v-else class="file-icon" :class="fileType(file.filename)"><component :is="fileIcons[fileType(file.filename)]" :size="22" /></span><span><button class="document-open" :disabled="busy" @click="openFile(file)"><strong>{{ file.title }}</strong></button><small>{{ fileType(file.filename) }}{{ file.filename && file.title !== file.filename ? ` · ${file.filename}` : '' }}</small><button v-if="file.permissions?.workflow" class="workflow-status" :class="{ 'requires-action': file.active_actions?.length }" :disabled="busy" :aria-label="`Zmień status: ${file.title}`" title="Zmień status dokumentu" @click="statusDocument = file">{{ file.status }}<ChevronDown :size="12" /></button><small v-else-if="file.active_actions?.length" class="workflow-readonly">{{ file.status }}</small><button v-if="file.approvals && Object.values(file.approvals).some(count => count > 0)" class="approval-summary" :class="{ accepted: file.approvals.accepted > 0 }" :disabled="busy" title="Akceptacje obecnej wersji pliku" @click="emailFile = file">Akceptacje: {{ file.approvals.accepted }}<span v-if="file.approvals.waiting"> · oczekuje {{ file.approvals.waiting }}</span><span v-if="file.approvals.failed"> · błędy {{ file.approvals.failed }}</span></button></span></span>
              <span class="muted file-size">{{ formatSize(file.file_size) }}</span><span class="muted date">{{ date(file.updated_at) }}</span>
              <div class="file-actions"><button v-if="file.can_share" class="icon-button" :disabled="busy" title="Udostępnij przez link zewnętrzny" :aria-label="`Udostępnij plik ${file.filename || file.title}`" @click="shareResource = { ...file, kind: 'document' }"><Share2 :size="18" /></button><button v-if="/\.pdf$/i.test(file.filename || '')" class="icon-button" :disabled="busy" aria-label="Podgląd PDF" title="Podgląd PDF" @click="pdfPreviewFile = file"><Eye :size="18" /></button><button class="icon-button" :disabled="busy" :aria-label="`Historia zmian: ${file.filename || file.title}`" title="Historia zmian" @click="historyTarget = { ...file, kind: 'document' }"><History :size="17" /></button><button class="icon-button" :disabled="busy" :aria-label="`Dodaj zadanie do pliku ${file.filename || file.title}`" title="Dodaj zadanie" @click="addResourceTask(file)"><ClipboardPlus :size="18" /></button><button v-if="canViewEmails(file)" class="icon-button" :disabled="busy" :aria-label="`Wyślij e-mailem i sprawdź akceptacje: ${file.filename}`" title="Wyślij e-mailem / akceptacje" @click="emailFile = file"><Mail :size="18" /></button><button v-if="fileType(file.filename) === 'Obrazy'" class="icon-button" :disabled="busy" :aria-label="`Obraz i metadane: ${file.filename}`" title="Kadrowanie, rozdzielczość i metadane" @click="imageEditorFile = file"><Image :size="18" /></button><button v-if="file.permissions?.edit && fileType(file.filename) !== 'Obrazy'" class="icon-button" :disabled="busy" :aria-label="`Edytuj opis pliku ${file.filename || file.title}`" :title="file.filename ? 'Edytuj opis' : 'Edytuj dokument'" @click="openDocument(file)"><Pencil :size="17" /></button><button v-if="!file.filename" class="download-button" :disabled="busy" :aria-label="`Pobierz PDF: ${file.title}`" title="Pobierz PDF" @click="downloadPdf(file)"><Download :size="19" /><span>PDF</span></button><a v-if="file.filename" class="download-button" :href="`/api/documents/${file.id}/file`" :aria-label="`Pobierz ${file.filename}`" title="Pobierz plik"><Download :size="19" /></a><button v-if="file.permissions?.delete" class="icon-button delete-button" :disabled="busy" :aria-label="`Usuń plik ${file.filename || file.title}`" title="Usuń plik" @click="deleteItem(file)"><Trash2 :size="18" /></button></div>
            </div>
            <div v-if="!filteredFiles.length && !filteredFolders.length" class="empty"><Folder :size="39" /><h2>{{ search || typeFilter !== 'Wszystkie' ? 'Brak wyników' : currentFolder ? 'Ten folder jest pusty' : 'Twój dysk jest gotowy' }}</h2><p class="muted">{{ search || typeFilter !== 'Wszystkie' ? 'Zmień wyszukiwanie lub typ pliku.' : canAddCurrent ? 'Dodaj pliki lub utwórz folder, aby je uporządkować.' : 'Brak dostępnych plików. Dostęp do folderów nadaje administrator.' }}</p><button v-if="canAddCurrent" class="primary" :disabled="busy" @click="openAddDocument"><Plus :size="17" /> Dodaj dokument</button></div>
          </section>
        </template>
        <ActiveDocuments v-else-if="view === 'active'" :documents="activeDocuments" :folders="folders" :busy="busy" @download-pdf="downloadPdf" @back="openDocumentsFolder" @refresh="run(loadDocuments)" @open-document="openFile" @open-image="imageEditorFile = $event" @open-email="emailFile = $event" @change-status="statusDocument = $event" @open-folder="openDriveFolder" />
        <AiCommands v-else-if="view === 'ai'" :api="api" :initial-prompt="startAiPrompt" @prompt-consumed="startAiPrompt = ''" />
        <SurveysPanel v-else-if="view === 'surveys'" :api="api" :initial-survey-id="startSurveyId" :initial-filter="surveyFilter" :initial-draft="startSurveyDraft" @draft-consumed="startSurveyDraft = null" @loaded="surveyData = $event" />
        <DictionariesPanel v-else-if="view === 'dictionaries'" :key="dictionaryRequest" :api="api" :initial-dictionary-id="selectedDictionaryId" @selected="selectedDictionaryId = $event" @updated="dictionaryRevision++" />
        <CalendarPanel v-else-if="view === 'calendar'" :api="api" :documents="documents" :folders="folders" @loaded="taskData = $event" @open-tasks="view = 'tasks'; search = ''" @open-document="openDocument" @open-folder="openDriveFolder" @new-task="taskTarget = {}" />
        <TasksPanel v-else-if="view === 'tasks'" @open-message="openMailAnalysisMessage" :api="api" :current-user="user" :documents="documents" :folders="folders" @open-folder="openDriveFolder" @loaded="taskData = $event" @updated="run(loadDocuments)" @open-document="openDocument" @open-email="emailFile = $event" />
        <template v-else-if="view === 'admin' && user.role === 'admin'"><AdminPanel :api="api" :current-user="user" @updated="refreshAccess" @impersonated="reloadWorkspace" /></template>
        <TemplatesPanel v-else @history="historyTarget = { ...$event, kind: 'template' }" :templates="templates" :api="api" :can-add="rootRights.add" @updated="run(loadDocuments)" @created-document="templateDocumentCreated" />
      </template>
    </main>
    </div>

    <div v-if="pwaDialog && user && !user.must_change_password && !user.impersonation" class="modal-backdrop pwa-backdrop"><PwaSettings :api="api" @close="pwaDialog = false" /></div>
    <div v-if="passwordDialog && user && !user.must_change_password" class="modal-backdrop"><PasswordChange :api="api" @close="passwordDialog = false" @saved="passwordSaved" /></div>
    <ResourceHistory v-if="historyTarget && user" :resource="historyTarget" :api="api" @close="historyTarget = null" />
    <ExternalShareDialog v-if="shareResource && user" :key="`${shareResource.kind}:${shareResource.id}`" :resource="shareResource" :api="api" @close="shareResource = null" />
    <AddDocumentDialog v-if="addDocumentDialog && user" :templates="templates" :api="api" :folder-id="currentFolder" :folder-name="currentFolderInfo?.name" @close="addDocumentDialog = false" @choose="chooseNewDocument" @upload="openUploadPicker" />
    <DocumentStatusDialog v-if="statusDocument && user" :document="statusDocument" :api="api" @close="statusDocument = null" @saved="statusSaved" />
    <TasksPanel v-if="taskTarget && user" dialog-only :initial-target="taskTarget" :api="api" :current-user="user" :documents="documents" :folders="folders" @close="taskTarget = null" @updated="run(loadDocuments)" />
    <FileEmailDialog v-if="emailFile && user" :file="emailFile" :api="api" @close="emailFile = null" @updated="emailUpdated" />
    <ImageEditor :task-data="taskData" v-if="imageEditorFile && user" :file="imageEditorFile" :api="api" @close="imageEditorFile = null" @saved="imageSaved" />
    <PdfPreview v-if="pdfPreviewFile && user" :file="pdfPreviewFile" :account-id="user.id" @close="pdfPreviewFile = null" />
    <div v-if="folderDialog" class="modal-backdrop">
      <section class="panel folder-dialog" role="dialog" aria-modal="true" aria-labelledby="folder-dialog-title">
        <div class="editor-heading"><h2 id="folder-dialog-title">{{ folderEditing ? 'Zmień nazwę folderu' : 'Dodaj katalog' }}</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="folderDialog = false"><X :size="21" /></button></div>
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
          <div class="editor-actions"><button type="button" :disabled="busy" @click="editor = null">Zamknij</button><button v-if="!editor.filename" type="button" :disabled="busy || !editor.title.trim()" :title="canEditEditor ? 'Zapisz dokument i pobierz PDF' : 'Pobierz PDF'" @click="downloadPdf(editor)"><Download :size="17" /> {{ canEditEditor ? 'Zapisz i pobierz PDF' : 'Pobierz PDF' }}</button><button v-if="canEditEditor" class="primary" :disabled="busy" type="submit"><Save :size="17" /> {{ busy ? 'Zapisywanie…' : 'Zapisz dokument' }}</button></div>
        </form>
      </section>
    </div>
  </div>
</template>
