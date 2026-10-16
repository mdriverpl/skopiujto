<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import MailSettings from './MailSettings.vue'
import { mailSenderKind } from './mailSenderKind.js'
import { Handshake, UserRound, Megaphone, Bell, Ban } from 'lucide-vue-next'
import { Mail, Search, Sparkles, Settings, Plus, Upload, RefreshCw, Star, Reply, Forward, Trash2, Archive, Paperclip, Inbox, Send, FileText, ShieldAlert, ShieldCheck, Building2, Landmark, HardDrive, FolderPlus, X, Download, ChevronLeft, List, LayoutGrid, CheckSquare, Lightbulb, AlertCircle, Pin } from 'lucide-vue-next'
const props = defineProps({ api: Function, initialFolder: String, folderRequest: Number, initialMessageId: String })
const emit = defineEmits(['folder-change', 'message-opened'])
const messages = ref([]), selectedId = ref(null), folder = ref(props.initialFolder || 'inbox'), filter = ref('all'), search = ref({ email: '', subject: '', content: '', filename: '' }), sort = ref('newest'), grid = ref(false)
watch(() => [props.initialFolder, props.folderRequest], ([next, request], previous) => {
  if (next && (next !== folder.value || request !== previous?.[1])) changeFolder(next)
})
watch(() => props.initialMessageId, async id => { if (id) { await run(load); await showRequestedMessage(id) } })
const headerSearch = ref('')
const categoryFilter = ref('')
const syncHours = ref(24)
const timeRanges = [{ hours: 24, label: '24 h' }, { hours: 48, label: '48 h' }, { hours: 168, label: '7 dni' }, { hours: 720, label: '30 dni' }]
async function changeTimeRange(hours) {
  if (busy.value || syncHours.value === hours) return
  syncHours.value = hours; selectedId.value = null
  await run(refresh)
}
const categories = { spam: 'Spam', advertisement: 'Reklama', invoice: 'Faktura', payment: 'Płatność', order: 'Zamówienie', newsletter: 'Newsletter', notification: 'Powiadomienie', correspondence: 'Korespondencja', other: 'Inne' }
const companies = ref([]), companyEditor = ref(null)
const driveDialog = ref(null), driveFolders = ref([]), driveAccess = ref({}), driveLoading = ref(false), driveSaving = ref(false), driveError = ref('')
function drivePath(id) {
  const parts = [], visited = new Set()
  while (id && !visited.has(id)) {
    visited.add(id)
    const item = driveFolders.value.find(folder => folder.id === id)
    if (!item) break
    parts.unshift(item.name); id = item.parent_id
  }
  return ['Mój dysk', ...parts].join(' / ')
}
const driveChoices = computed(() => driveFolders.value.map(item => ({ ...item, path: drivePath(item.id) })).sort((a, b) => a.path.localeCompare(b.path, 'pl')))
const driveTargetRights = computed(() => driveDialog.value?.destination ? driveFolders.value.find(item => item.id === driveDialog.value.destination)?.permissions : driveAccess.value)
const canSaveToDrive = computed(() => !!driveDialog.value?.chosen.length && driveTargetRights.value?.read && driveTargetRights.value?.add && !driveLoading.value && !driveSaving.value && (!driveDialog.value.createFolder || !!driveDialog.value.newName.trim()))
const busy = ref(false), error = ref(''), notice = ref(''), settings = ref(null), showSettings = ref(false), composer = ref(null), analysis = ref({}), aiBusy = ref(false), importInput = ref(null)
const spamFeedback = ref(false)
const folders = [
  { id: 'inbox', label: 'Odebrane', icon: Inbox }, { id: 'sent', label: 'Wysłane', icon: Send },
  { id: 'drafts', label: 'Robocze', icon: FileText }, { id: 'archive', label: 'Archiwum', icon: Archive },
  { id: 'spam', label: 'Spam', icon: ShieldAlert }, { id: 'trash', label: 'Śmieci', icon: Trash2 }
]
const filters = [{ id: 'all', label: 'Wszystkie' }, { id: 'unread', label: 'Nieprzeczytane' }, { id: 'urgent', label: 'Pilne' }, { id: 'reply', label: 'Do odpowiedzi' }, { id: 'payment', label: 'Do zapłaty' }, { id: 'attachments', label: 'Załączniki' }]
const labels = { urgent: 'Pilne', invoice: 'Faktura', offer: 'Oferta', reply: 'Do odpowiedzi', payment: 'Do zapłaty', info: 'Informacja' }
const labelChoices = { urgent: 'Pilne', invoice: 'Faktura', offer: 'Oferta' }
const labelPopup = ref(null), labelPopupStyle = ref({})
const labelTargetId = ref(null)
const labelTarget = computed(() => messages.value.find(message => message.id === labelTargetId.value))
watch(selectedId, () => labelPopup.value?.hidePopover())
function positionLabelMenu(event, message = selected.value) {
  if (!message) return
  labelTargetId.value = message.id
  const rect = event.currentTarget.getBoundingClientRect()
  const width = 200, height = 210
  labelPopupStyle.value = {
    left: `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`,
    top: `${rect.bottom + height + 8 > window.innerHeight ? Math.max(8, rect.top - height - 6) : rect.bottom + 6}px`
  }
}
async function chooseLabel(label) {
  const message = labelTarget.value
  if (!message) return
  await run(() => patch(message, { label }))
  if (!error.value) labelPopup.value?.hidePopover()
}
const selected = computed(() => messages.value.find(m => m.id === selectedId.value))
const currentAnalysis = computed(() => analysis.value[selectedId.value])
const inbox = computed(() => messages.value.filter(m => m.folder === 'inbox'))
const unread = computed(() => inbox.value.filter(m => m.unread).length)
const matches = (value, query) => (value || '').toLocaleLowerCase('pl').includes(query.trim().toLocaleLowerCase('pl'))
function clearSearch() { search.value = { email: '', subject: '', content: '', filename: '' } }
const filtered = computed(() => messages.value.filter(m => m.folder === folder.value)
  .filter(m => !categoryFilter.value || (categoryFilter.value === 'uncategorized' ? !m.category : m.category === categoryFilter.value))
  .filter(m => filter.value === 'all' || (filter.value === 'unread' ? m.unread : filter.value === 'attachments' ? m.attachments.length : m.label === filter.value))
  .filter(m => !headerSearch.value.trim() || [m.sender_name, m.sender_email, m.recipient, m.subject, m.content, ...m.attachments.map(part => part.name)].some(value => matches(value, headerSearch.value)))
  .filter(m => (!search.value.email.trim() || [m.sender_email, m.recipient].some(value => matches(value, search.value.email)))
    && matches(m.subject, search.value.subject)
    && matches(m.content, search.value.content)
    && (!search.value.filename.trim() || m.attachments.some(part => matches(part.name, search.value.filename))))
  .sort((a, b) => (sort.value === 'newest' ? -1 : 1) * (Date.parse(a.created_at) - Date.parse(b.created_at))))
const initials = m => (m.sender_name || m.sender_email || '?').split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase()
const senderKinds = {
  company: { icon: Handshake, label: 'Firma / klient', hint: 'Adres lub domena przypisane do firmy' },
  government: { icon: Landmark, label: 'Domena rządowa', hint: 'Rozpoznana domena rządowa; autentyczność e-maila niepotwierdzona' },
  other: { icon: UserRound, label: 'Pozostały nadawca', hint: 'Adres nieprzypisany do firmy ani rozpoznanej domeny rządowej' },
  marketing: { icon: Megaphone, label: 'Reklama / newsletter', hint: 'Wiadomość z kategorią reklamy lub newslettera' },
  notification: { icon: Bell, label: 'Powiadomienie', hint: 'Wiadomość z kategorią powiadomienia' },
  phishing: { icon: ShieldAlert, label: 'Podejrzenie phishingu', hint: 'Wykryto sygnały próby wyłudzenia danych' },
  spam: { icon: Ban, label: 'Spam', hint: 'Wiadomość w Spamie lub od zablokowanego adresu' },
  sent: { icon: Send, label: 'Wysłana', hint: 'Wiadomość wysłana przez Ciebie' },
  draft: { icon: FileText, label: 'Robocza', hint: 'Niewysłany szkic wiadomości' }
}
const date = value => new Date(value).toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' })
const fullDate = value => new Date(value).toLocaleString('pl-PL', { dateStyle: 'medium', timeStyle: 'short' })
const size = value => value < 1024 ? `${value} B` : value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
function replace(message) { messages.value = [message, ...messages.value.filter(m => m.id !== message.id)] }
async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''; spamFeedback.value = false
  try { return await action() } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function load() {
  const include = props.initialMessageId || selectedId.value
  const path = `/client-mail?hours=${syncHours.value}` + (include ? `&include_id=${encodeURIComponent(include)}` : '')
  const result = await Promise.all([props.api(path), props.api('/client-mail/settings')])
  messages.value = result[0]; settings.value = result[1]
  if (!selected.value) selectedId.value = null
}
async function refresh() {
  if (!settings.value) settings.value = await props.api('/client-mail/settings')
  if (!settings.value.account.imap.enabled) {
    await load()
    notice.value = 'Aby odbierać wiadomości, włącz IMAP w ustawieniach poczty.'
    return
  }
  const result = await props.api('/client-mail/sync', 'POST', { hours: syncHours.value })
  await load()
  notice.value = `Pobrano wiadomości: ${result.imported}.` + (result.remaining ? ` Pozostało: ${result.remaining}. Odśwież ponownie.` : '') + (result.skipped ? ` Pominięto zbyt duże lub niepoprawne wiadomości: ${result.skipped}.` : '')
}
async function scanSpam() {
  const result = await props.api(`/client-mail/spam-scan?hours=${syncHours.value}`, 'POST')
  await load()
  if (selected.value?.folder === 'spam' && folder.value !== 'spam') selectedId.value = null
  if (result.moved) {
    spamFeedback.value = true
    notice.value = `Filtr lokalny przeniósł do Spamu: ${result.moved}. Pominięto zaufane adresy i domeny.`
  }
}
async function patch(message, changes) {
  const result = await props.api(`/client-mail/${message.id}`, 'PATCH', { version: message.version, ...changes })
  replace(result)
  if (changes.folder === 'spam' && message.folder !== 'spam') {
    if (selectedId.value === message.id) selectedId.value = null
    spamFeedback.value = true; notice.value = 'Przeniesiono wiadomość do Spamu.'
  }
  return result
}
async function editCompany() {
  const message = selected.value
  await run(async () => {
    companies.value = await props.api('/client-mail/companies')
    companyEditor.value = { messageId: message.id, version: message.version, address: message.sender_email,
      scope: 'email', entry_id: message.company?.id || '', linkedCompany: message.company || null, name: '' }
  })
}
async function saveCompany() {
  await run(async () => {
    const draft = companyEditor.value
    const result = await props.api(`/client-mail/${draft.messageId}/company`, 'POST', {
      version: draft.version, scope: draft.scope, entry_id: draft.entry_id || null, name: draft.name
    })
    replace(result); companyEditor.value = null
    await load()
    notice.value = 'Przypisano firmę. Powiązane wiadomości są oznaczone jako bezpieczne.'
  })
}
async function removeCompany() {
  const draft = companyEditor.value
  const message = draft ? { id: draft.messageId, version: draft.version, company: draft.linkedCompany } : selected.value
  if (!message?.company) return
  await run(async () => {
    const result = await props.api(`/client-mail/${message.id}/company`, 'DELETE', {
      version: message.version, entry_id: message.company.id
    })
    replace(result); companyEditor.value = null
    await load()
    notice.value = 'Usunięto przypisanie tego adresu e-mail do firmy. Firma pozostała w słowniku; inne adresy i reguła domeny pozostają bez zmian.'
  })
}
async function spamSender() {
  const message = selected.value
  if (!message || message.safe || message.company || message.spam_protected) return
  await run(async () => {
    await props.api(`/client-mail/${message.id}/spam-address`, message.blocked ? 'DELETE' : 'POST', { version: message.version })
    await load()
    if (!message.blocked) { selectedId.value = null; spamFeedback.value = true }
    notice.value = message.blocked ? 'Usunięto adres z listy spamu.' : 'Adres dodano do spamu. Kolejne wiadomości od tego nadawcy trafią do Spamu.'
  })
}
function changeFolder(id) { folder.value = id; selectedId.value = null; filter.value = 'all'; categoryFilter.value = ''; emit('folder-change', id) }
async function open(message) {
  if (busy.value) return
  selectedId.value = message.id
  if (message.folder === 'drafts') { compose(message); return }
  if (message.unread) await run(() => patch(message, { unread: false }))
}
async function showRequestedMessage(id) {
  const message = messages.value.find(item => item.id === id)
  if (!message) error.value = 'Wiadomość nie jest już dostępna. Wróć do analizy i odśwież raport.'
  else { changeFolder(message.folder); headerSearch.value = ''; clearSearch(); await open(message) }
  emit('message-opened')
}
function compose(message = null, mode = 'draft') {
  error.value = ''; notice.value = ''
  if (message && mode === 'draft') { composer.value = { ...message }; return }
  const forward = mode === 'forward'
  composer.value = { recipient: message && !forward ? message.sender_email : '',
    subject: message ? `${forward ? 'Fwd: ' : /^Re:/i.test(message.subject) ? '' : 'Re: '}${message.subject}` : '',
    content: message ? `\n\n---------- ${forward ? 'Przekazana wiadomość' : 'Wiadomość oryginalna'} ----------\nOd: ${message.sender_name} <${message.sender_email}>\nTemat: ${message.subject}\n\n${message.content}` : '' }
}
async function saveDraft() {
  const draft = composer.value
  const saved = await props.api(draft.id ? `/client-mail/${draft.id}/draft` : '/client-mail/drafts', draft.id ? 'PUT' : 'POST',
    { recipient: draft.recipient, subject: draft.subject, content: draft.content, ...(draft.id ? { version: draft.version } : {}) })
  replace(saved); composer.value = { ...saved }; return saved
}
async function save() { await run(async () => { await saveDraft(); composer.value = null; notice.value = 'Szkic został zapisany w folderze Robocze.' }) }
async function send() {
  await run(async () => {
    const draft = await saveDraft()
    const sent = await props.api(`/client-mail/${draft.id}/send`, 'POST', { version: draft.version })
    replace(sent); composer.value = null; notice.value = 'Serwer SMTP przyjął wiadomość do wysłania.'; changeFolder('sent'); selectedId.value = sent.id
  })
}
async function importMail(event) {
  const file = event.target.files?.[0]; if (!file) return
  await run(async () => {
    if (file.size > 10 * 1024 * 1024) throw new Error('Maksymalny rozmiar wiadomości to 10 MB.')
    const data = new FormData(); data.append('file', file)
    const message = await props.api('/client-mail/import', 'POST', data)
    replace(message); changeFolder(message.folder); selectedId.value = message.id; notice.value = 'Wiadomość została zaimportowana.'
  })
  event.target.value = ''
}
async function analyze() {
  const message = selected.value
  if (!message || aiBusy.value) return
  aiBusy.value = true; error.value = ''
  try { analysis.value = { ...analysis.value, [message.id]: await props.api(`/client-mail/${message.id}/analysis`, 'POST') } }
  catch (err) { error.value = err.message } finally { aiBusy.value = false }
}
function useReply() { compose(selected.value, 'reply'); composer.value.content = currentAnalysis.value.reply }
async function download(part) {
  if (selected.value?.attachments_blocked) return
  await run(async () => {
    const response = await fetch(`/api/client-mail/${selected.value.id}/attachments/${part.id}`, { credentials: 'same-origin' })
    if (!response.ok) {
      const detail = await response.json().catch(() => null)
      throw new Error(detail?.detail || 'Nie udało się pobrać załącznika.')
    }
    const url = URL.createObjectURL(await response.blob()), a = document.createElement('a')
    a.href = url; a.download = part.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
}
async function openDriveDialog(part = null) {
  if (!selected.value || selected.value.attachments_blocked || driveSaving.value) return
  const message = selected.value
  const dialog = { mailId: message.id, attachments: message.attachments.map(item => ({ ...item })),
    chosen: part ? [part.id] : message.attachments.map(item => item.id), destination: null,
    createFolder: false, newName: '', saved: [] }
  driveDialog.value = dialog; driveFolders.value = []; driveAccess.value = {}; driveError.value = ''; driveLoading.value = true
  const current = driveDialog.value
  try {
    const [folders, rights] = await Promise.all([props.api('/folders'), props.api('/access')])
    if (driveDialog.value !== current) return
    driveFolders.value = folders; driveAccess.value = rights
    if (!rights.read || !rights.add) current.destination = folders.find(item => item.permissions?.read && item.permissions?.add)?.id || null
    if (!driveTargetRights.value?.read || !driveTargetRights.value?.add) driveError.value = 'Nie masz uprawnień do zapisu w dostępnych katalogach Dysku.'
  } catch (err) { if (driveDialog.value === current) driveError.value = err.message }
  finally { if (driveDialog.value === current) driveLoading.value = false }
}
function closeDriveDialog() { if (!driveSaving.value) { driveDialog.value = null; driveLoading.value = false } }
async function saveToDrive() {
  if (!canSaveToDrive.value) return
  const dialog = driveDialog.value
  driveSaving.value = true; driveError.value = ''
  try {
    if (dialog.createFolder) {
      const permissions = { ...driveTargetRights.value }
      const created = await props.api('/folders', 'POST', { name: dialog.newName.trim(), parent_id: dialog.destination, access_mode: 'inherit' })
      driveFolders.value = [...driveFolders.value, { ...created, permissions }]
      dialog.destination = created.id; dialog.createFolder = false; dialog.newName = ''
    }
    const chosen = [...dialog.chosen]
    for (const id of chosen) {
      const part = dialog.attachments.find(item => item.id === id)
      const response = await fetch(`/api/client-mail/${dialog.mailId}/attachments/${id}`, { credentials: 'same-origin' })
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail || `Nie udało się odczytać załącznika „${part.name}”.`)
      }
      const file = await response.blob()
      const data = new FormData(); data.append('file', file, part.name)
      if (dialog.destination) data.append('folder_id', dialog.destination)
      await props.api('/files', 'POST', data)
      dialog.saved.push({ id, name: part.name, path: drivePath(dialog.destination) })
      dialog.chosen = dialog.chosen.filter(item => item !== id)
    }
    notice.value = `Zapisano załączniki na Dysku portalu: ${dialog.saved.length}. Katalog: ${drivePath(dialog.destination)}.`
    driveDialog.value = null
  } catch (err) {
    driveError.value = err.message + (dialog.saved.length ? ` Zapisano już: ${dialog.saved.length}. Ponów zapis pozostałych załączników.` : '')
  } finally { driveSaving.value = false }
}
onMounted(async () => { await run(async () => { try { await scanSpam() } catch (err) { await load(); throw err } }); if (props.initialMessageId) await showRequestedMessage(props.initialMessageId) })
</script>

<template>
  <section class="client-mail" aria-label="Poczta">
    <div class="mail-heading">
      <Teleport to="#workspace-title"><div class="mail-title"><span class="mail-logo"><Mail :size="24" /></span><div><div class="mail-title-line"><h1>Poczta</h1><button class="mail-icon" aria-label="Ustawienia konta pocztowego" title="Ustawienia konta pocztowego" @click="showSettings = true"><Settings :size="19" /></button></div><small>Twoja korespondencja, uporządkowana.</small></div></div></Teleport>
      <Teleport to="#workspace-search"><label class="mail-search"><Search :size="19" /><input v-model="headerSearch" type="search" aria-label="Szukaj w wiadomościach po temacie, adresie e-mail, treści lub nazwie pliku" placeholder="Szukaj w wiadomościach: temat, e-mail, treść, pliki…" /></label></Teleport>
    </div>
    <p v-if="error" class="mail-error" role="alert">{{ error }}</p><p v-if="notice" class="mail-notice" :class="{ 'mail-spam-notice': spamFeedback }" role="status"><span v-if="spamFeedback" class="mail-spam-flight" aria-hidden="true"><Mail class="mail-flying-envelope" :size="20" /><ShieldAlert class="mail-spam-destination" :size="24" /></span>{{ notice }}</p>
    <div class="mail-layout" :class="{ 'message-open': selected }">
      <aside class="mail-list-panel">
        <div class="mail-list-heading"><span class="mail-folder-title">{{ folders.find(f => f.id === folder)?.label }} <small>{{ filtered.length }}</small><button class="mail-icon" :disabled="busy" aria-label="Odśwież pocztę" title="Odśwież pocztę" @click="run(refresh)"><RefreshCw :size="17" /></button></span><div><button class="mail-icon" :disabled="busy" aria-label="Importuj wiadomość .eml" @click="importInput.click()" title="Importuj wiadomość .eml"><Upload :size="17" /></button><button class="mail-new" title="Napisz nową wiadomość" :disabled="busy" @click="compose()"><Plus :size="16" /> Napisz</button></div></div>
        <div class="mail-time-range" role="group" aria-label="Zakres pobierania i listy wiadomości"><span>Ostatnie</span><button v-for="range in timeRanges" :key="range.hours" :disabled="busy" :aria-pressed="syncHours === range.hours" :title="`Pobierz i pokaż wiadomości z ostatnich ${range.label}`" @click="changeTimeRange(range.hours)">{{ range.label }}</button><RefreshCw v-if="busy" class="mail-range-loading" :size="14" aria-label="Wczytywanie poczty" /></div>
        <input ref="importInput" type="file" accept=".eml" hidden aria-label="Plik wiadomości .eml" @change="importMail" />
        <div class="mail-message-list" :class="{ tiles: grid }" aria-label="Lista wiadomości">
          <article v-for="message in filtered" :key="message.id" class="mail-row" :class="{ selected: selectedId === message.id, unread: message.unread }">
            <button class="mail-row-open" :title="`Otwórz wiadomość: ${message.subject || '(bez tematu)'}`" :disabled="busy" @click="open(message)"><span class="mail-sender-symbol" :class="'sender-' + mailSenderKind(message)" role="img" :aria-label="senderKinds[mailSenderKind(message)].label" :title="senderKinds[mailSenderKind(message)].hint"><component :is="senderKinds[mailSenderKind(message)].icon" :size="25" :stroke-width="1.7" aria-hidden="true" /></span><span class="mail-row-text"><strong>{{ folder === 'sent' || folder === 'drafts' ? message.recipient || 'Brak odbiorcy' : message.sender_name }}</strong><span v-if="message.company || message.government" class="mail-row-affiliations"><span v-if="message.company" class="mail-row-company" :title="`Firma: ${message.company.name}`"><Building2 :size="12" /><span>{{ message.company.name }}</span></span><span v-if="message.government" class="mail-row-government" :title="`Domena rządowa: ${message.government.domain} · ${message.government.country}. Autentyczność wiadomości niepotwierdzona.`"><Landmark :size="12" /><span>{{ message.government.suffix }} · {{ message.government.country }}</span></span></span><span>{{ message.subject || '(bez tematu)' }}</span><small>{{ message.content || 'Pusty szkic' }}</small></span></button>
            <div class="mail-row-meta"><span v-if="message.category" class="mail-category" :class="message.category" :title="message.category_reason || categories[message.category]">{{ categories[message.category] }}</span><time :datetime="message.created_at">{{ date(message.created_at) }}</time><button class="mail-icon star" :class="{ starred: message.starred }" :disabled="busy" :aria-label="message.starred ? 'Usuń gwiazdkę' : 'Oznacz gwiazdką'" :aria-pressed="!!message.starred" @click="run(() => patch(message, { starred: !message.starred }))" :title="message.starred ? 'Usuń gwiazdkę' : 'Oznacz gwiazdką'"><Star :size="17" /></button><button class="mail-tag mail-row-label" :class="message.label || 'none'" :disabled="busy" :title="`Etykieta: ${labels[message.label] || 'Brak'}`" :aria-label="`Zmień etykietę: ${message.subject || '(bez tematu)'}`" popovertarget="mail-label-options" @click.stop="positionLabelMenu($event, message)">{{ labels[message.label] || 'Brak' }}</button><Paperclip v-if="message.attachments.length" :size="14" /></div>
          </article>
          <div v-if="!filtered.length" class="mail-list-empty"><Inbox :size="35" /><h2>{{ busy ? 'Wczytywanie poczty…' : 'Brak wiadomości' }}</h2><p>{{ messages.length ? 'Zmień folder, filtr lub wyszukiwanie.' : 'Importuj wiadomość .eml lub napisz pierwszego maila.' }}</p><button v-if="!messages.length" :disabled="busy" title="Importuj plik EML z załącznikami" @click="importInput.click()"><Upload :size="16" /> Importuj .eml</button></div>
        </div>
      </aside>
      <section class="mail-reader" aria-label="Podgląd wiadomości">
        <template v-if="selected">
          <div class="mail-reader-toolbar"><button class="mobile-back mail-icon" aria-label="Wróć do listy" @click="selectedId = null" title="Wróć do listy"><ChevronLeft :size="18" /></button><button :disabled="busy" title="Odpowiedz nadawcy wiadomości" @click="compose(selected, 'reply')"><Reply :size="17" /> Odpowiedz</button><button :disabled="busy" title="Przekaż treść wiadomości innemu odbiorcy" @click="compose(selected, 'forward')"><Forward :size="17" /> Przekaż dalej</button><button v-if="!selected.safe && !selected.company && !selected.spam_protected" class="mail-spam-button" :disabled="busy || !selected.sender_email" :title="selected.blocked ? 'Zezwól na nowe wiadomości od tego adresu' : 'Przenieś korespondencję od tego adresu do Spamu i blokuj kolejne wiadomości'" @click="spamSender"><ShieldAlert :size="17" />{{ selected.blocked ? 'Usuń ze spamu' : 'SPAM' }}</button><button :disabled="busy" aria-label="Przenieś do śmieci" @click="run(() => patch(selected, { folder: 'trash' }))" title="Przenieś do śmieci"><Trash2 :size="17" /></button><button :disabled="busy" aria-label="Archiwizuj" @click="run(() => patch(selected, { folder: 'archive' }))" title="Archiwizuj"><Archive :size="17" /></button></div>
          <div class="mail-reader-content">
          <p v-if="selected.phishing_warning || (!selected.safe && selected.category_reason?.startsWith('Podejrzenie phishingu:'))" class="mail-phishing-warning" role="alert"><ShieldAlert :size="20" /><span>{{ selected.phishing_warning || selected.category_reason }}</span></p>
          <div class="mail-sender"><span class="mail-avatar tone-0">{{ initials(selected) }}</span><div><small>Od: {{ selected.sender_name }}</small>
            <div class="mail-sender-address"><strong>{{ selected.sender_email }}</strong><template v-if="selected.company"><button class="mail-company" :disabled="busy" title="Zmień przypisanie adresu lub domeny do firmy" @click="editCompany"><Building2 :size="15" />{{ selected.company.name }}</button></template><template v-else><button :disabled="busy || !selected.sender_email" title="Przypisz adres e-mail lub jego domenę do firmy" @click="editCompany"><Building2 :size="15" /> Przypisz firmę</button><button v-if="!selected.safe && !selected.company && !selected.spam_protected" class="mail-spam-button" :disabled="busy || !selected.sender_email" :title="selected.blocked ? 'Usuń adres z listy spamu' : 'Oznacz adres jako spam i przenieś jego wiadomości do Spamu'" @click="spamSender"><ShieldAlert :size="15" />{{ selected.blocked ? 'Usuń ze spamu' : 'SPAM' }}</button></template></div>
            <div v-if="selected.government" class="mail-government"><span><Building2 :size="16" /> Domena rządowa · {{ selected.government.country }} <strong>{{ selected.government.domain }}</strong></span><small>Rozpoznano domenę w adresie nadawcy. Autentyczność wiadomości niepotwierdzona.</small><small v-if="selected.government.spam_protected">Domena gov.pl jest chroniona przed oznaczeniem jako spam.</small></div>
            <div class="mail-inline-label"><span>Etykieta:</span><button class="mail-label-trigger" :class="selected.label || 'none'" :disabled="busy" aria-label="Etykieta wiadomości" title="Wybierz etykietę wiadomości" popovertarget="mail-label-options" @click="positionLabelMenu"><span>{{ labels[selected.label] || 'Brak' }}</span><ChevronLeft :size="14" /></button></div>

            <span v-if="selected.safe" class="mail-safe" title="Nadawca przypisany do firmy w Twoim słowniku"><ShieldCheck :size="15" /> Bezpieczna · przypisana firma</span><span v-else-if="selected.blocked" class="mail-blocked"><ShieldAlert :size="15" /> Adres na liście spamu</span><small>Do: {{ selected.recipient || 'mnie' }}</small>
          </div><time :datetime="selected.created_at">{{ fullDate(selected.created_at) }}</time></div>
          <div class="mail-subject"><h2>{{ selected.subject || '(bez tematu)' }}</h2><span v-if="selected.category" class="mail-category" :class="selected.category" :title="selected.category_reason || 'Kategoria wiadomości'">{{ categories[selected.category] }}</span><span v-if="selected.label" class="mail-tag" :class="selected.label">{{ labels[selected.label] }}</span></div>
          <div class="mail-body">{{ selected.content }}</div>

          </div>
        </template>
        <div v-else class="mail-reader-empty"><span><Mail :size="42" /></span><h2>Miejsce na Twoją korespondencję</h2><p>Wybierz wiadomość, aby przeczytać jej treść,<br />pobrać załączniki i przygotować odpowiedź.</p><button class="primary" title="Utwórz nową wiadomość e-mail" @click="compose()"><Plus :size="17" /> Nowa wiadomość</button></div>
      </section>
      <aside class="mail-ai mail-side-panel" aria-label="Załączniki i działania wiadomości">
        <template v-if="selected">
          <section class="mail-side-attachments" aria-label="Załączniki wiadomości"><h2><Paperclip :size="18" /> Załączniki <small>{{ selected.attachments.length }}</small></h2>
            <p v-if="selected.attachments_blocked" class="mail-side-empty">Załączniki spamu nie są pobierane ani zapisywane. Aby uzyskać dostęp do pliku, najpierw przywróć wiadomość do Odebranych.</p>
            <div v-else-if="selected.attachments.length" class="mail-attachments">
              <div v-for="part in selected.attachments" :key="part.id" class="mail-attachment-card"><div class="mail-file-description"><FileText class="attachment-icon" :size="23" /><span>{{ part.name }}<small>{{ size(part.size) }}</small></span></div><div class="mail-file-actions"><button :disabled="busy" :aria-label="`Pobierz na komputer: ${part.name}`" :title="`Pobierz na komputer: ${part.name}`" @click="download(part)"><Download :size="18" /></button><button :disabled="busy || driveSaving" :aria-label="`Zapisz na Dysku portalu: ${part.name}`" :title="`Zapisz na Dysku portalu: ${part.name}`" @click="openDriveDialog(part)"><HardDrive :size="18" /></button></div></div>
              <button class="mail-save-all" :disabled="busy || driveSaving" title="Wybierz katalog na Dysku portalu i zapisz wszystkie załączniki" @click="openDriveDialog()"><HardDrive :size="16" /> Zapisz wszystkie na Dysku</button>
            </div><p v-else class="mail-side-empty">Ta wiadomość nie ma załączników.</p>
          </section>
        </template><p v-else class="mail-side-empty">Wybierz wiadomość, aby zobaczyć załączniki.</p>
        <details v-if="selected" class="mail-group ai-group">
          <summary title="Rozwiń lub zwiń analizę wiadomości przez AI"><Sparkles :size="20" /><span>Analiza AI</span><ChevronLeft class="group-chevron" :size="17" /></summary>
          <div class="mail-group-content"><template v-if="currentAnalysis"><div class="ai-card"><h3><Pin :size="17" /> Podsumowanie</h3><p>{{ currentAnalysis.summary }}</p></div><div class="ai-card priority-card"><h3><AlertCircle :size="17" /> Priorytet <span class="mail-tag" :class="currentAnalysis.priority === 'high' ? 'urgent' : 'info'">{{ currentAnalysis.priority === 'high' ? 'Wysoki' : 'Normalny' }}</span></h3></div><div class="ai-card"><h3><CheckSquare :size="17" /> Wykryte zadania</h3><ul v-if="currentAnalysis.tasks.length"><li v-for="task in currentAnalysis.tasks" :key="task">{{ task }}</li></ul><p v-else>Nie wykryto zadań.</p></div><div v-if="selected?.attachments.length" class="ai-card"><h3><Paperclip :size="17" /> Załączniki</h3><span v-for="part in selected.attachments" :key="part.id" class="ai-attachment">{{ part.name }}</span></div><div class="ai-card"><h3><Lightbulb :size="18" /> Proponowana odpowiedź</h3><p class="ai-reply">{{ currentAnalysis.reply }}</p><button class="ai-action" :disabled="busy" title="Wstaw propozycję AI do nowego szkicu odpowiedzi" @click="useReply"><Reply :size="17" /> Użyj odpowiedzi</button></div></template>
        <div v-else class="ai-intro"><span class="ai-orb"><Sparkles :size="30" /></span><h3>Mniej czytania.<br />Więcej konkretów.</h3><p>Podsumowanie, priorytet, zadania i propozycja odpowiedzi w jednym miejscu.</p></div>
        <button class="ai-action" :disabled="!selected || aiBusy || !settings?.ai.available" title="Przeanalizuj treść wybranej wiadomości przez AI" @click="analyze"><Sparkles :size="17" />{{ aiBusy ? 'Analizowanie…' : currentAnalysis ? 'Analizuj ponownie' : 'Przeanalizuj wiadomość' }}</button><small class="ai-footnote">{{ settings && !settings.ai.available ? settings.ai.message : 'Analiza przesyła treść wybranej wiadomości do AI. Sprawdź propozycję przed wysłaniem.' }}</small>
          </div>
        </details>
      </aside>
    </div>
    <div id="mail-label-options" ref="labelPopup" popover="auto" role="group" aria-label="Wybierz etykietę" class="mail-label-popup" :style="labelPopupStyle"><button :disabled="busy" :aria-pressed="!labelTarget?.label" @click="chooseLabel('')"><span class="mail-label-dot none"></span>Brak<span v-if="!labelTarget?.label" class="mail-label-check">✓</span></button><button v-for="(name, key) in labelChoices" :key="key" :disabled="busy" :aria-pressed="labelTarget?.label === key" @click="chooseLabel(key)"><span class="mail-label-dot" :class="key"></span>{{ name }}<span v-if="labelTarget?.label === key" class="mail-label-check">✓</span></button></div>
    <MailSettings v-if="showSettings" :api="api" :initial="settings" @close="showSettings = false" @saved="settings = $event" />
    <div v-if="driveDialog" class="mail-modal" @keydown.esc="closeDriveDialog"><form class="mail-dialog mail-drive-dialog" role="dialog" aria-modal="true" aria-labelledby="mail-drive-title" @submit.prevent="saveToDrive"><header><h2 id="mail-drive-title"><HardDrive :size="21" /> Zapisz załączniki na Dysku</h2><button type="button" class="mail-icon" :disabled="driveSaving" title="Zamknij wybór katalogu" aria-label="Zamknij wybór katalogu" @click="closeDriveDialog"><X :size="20" /></button></header>
      <p v-if="driveLoading" role="status">Wczytywanie katalogów Dysku…</p><p v-if="driveError" class="mail-error" role="alert">{{ driveError }}</p>
      <template v-if="!driveLoading"><fieldset :disabled="driveSaving"><legend>Załączniki do zapisania</legend><label v-for="part in driveDialog.attachments" :key="part.id" class="mail-drive-file"><input v-model="driveDialog.chosen" type="checkbox" :value="part.id" :disabled="driveDialog.saved.some(item => item.id === part.id)" /><span>{{ part.name }}<small>{{ driveDialog.saved.some(item => item.id === part.id) ? 'Zapisano na Dysku' : size(part.size) }}</small></span></label></fieldset>
      <label>{{ driveDialog.createFolder ? 'Utwórz katalog w' : 'Katalog docelowy' }}<select v-model="driveDialog.destination" :disabled="driveSaving"><option :value="null" :disabled="!driveAccess.read || !driveAccess.add">Mój dysk</option><option v-for="item in driveChoices" :key="item.id" :value="item.id" :disabled="!item.permissions?.read || !item.permissions?.add">{{ item.path }}{{ !item.permissions?.add ? ' — brak zapisu' : '' }}</option></select></label>
      <button type="button" class="mail-drive-new" :disabled="driveSaving || !driveTargetRights?.add" :aria-expanded="driveDialog.createFolder" title="Utwórz nowy katalog w wybranym miejscu" @click="driveDialog.createFolder = !driveDialog.createFolder"><FolderPlus :size="17" />{{ driveDialog.createFolder ? 'Wybierz istniejący katalog' : 'Dodaj nowy katalog' }}</button>
      <label v-if="driveDialog.createFolder">Nazwa nowego katalogu<input v-model="driveDialog.newName" required maxlength="120" :disabled="driveSaving" placeholder="np. Załączniki od klientów" /></label>
      <p class="ai-footnote">Zapis do „Mojego dysku” w portalu. Pliki będą dostępne dla osób z uprawnieniami do wybranego katalogu.</p><ul v-if="driveDialog.saved.length" class="mail-drive-saved"><li v-for="item in driveDialog.saved" :key="item.id">{{ item.name }} — {{ item.path }}</li></ul></template>
      <p v-if="driveSaving" role="status">Zapisywanie załączników… Zapisano: {{ driveDialog.saved.length }}.</p><footer><button type="button" :disabled="driveSaving" @click="closeDriveDialog">Anuluj</button><button class="primary" :disabled="!canSaveToDrive"><HardDrive :size="17" />{{ driveSaving ? 'Zapisywanie…' : `Zapisz na Dysku (${driveDialog.chosen.length})` }}</button></footer></form></div>
    <div v-if="companyEditor" class="mail-modal"><form class="mail-dialog company-dialog" role="dialog" aria-modal="true" aria-labelledby="company-title" @submit.prevent="saveCompany"><header><h2 id="company-title">Przypisz firmę</h2><button type="button" class="mail-icon" :disabled="busy" aria-label="Zamknij przypisanie firmy" title="Zamknij przypisanie firmy" @click="companyEditor = null"><X :size="20" /></button></header><p v-if="error" class="mail-error" role="alert">{{ error }}</p><p class="company-address">{{ companyEditor.address }}</p><label>Zakres przypisania<select v-model="companyEditor.scope" :disabled="busy"><option value="email">Tylko ten adres e-mail</option><option value="domain">Wszystkie adresy w tej domenie</option></select></label><label>Firma ze słownika<select v-model="companyEditor.entry_id" :disabled="busy"><option value="">Dodaj nową firmę</option><option v-for="item in companies" :key="item.id" :value="item.id">{{ item.name || '(bez nazwy)' }}</option></select></label><label v-if="!companyEditor.entry_id">Nazwa firmy<input v-model="companyEditor.name" required maxlength="200" :disabled="busy" placeholder="np. Biuro Rachunkowe Kowalski" /></label><p class="ai-footnote">Nowa firma zostanie dopisana do słownika Firmy. Jeśli słownika nie ma, powstanie automatycznie. Powiązane wiadomości zostaną uznane za bezpieczne, a te w Spamie wrócą do Odebranych. Osobne przypisanie adresu ma pierwszeństwo przed domeną.</p><footer><button v-if="companyEditor.linkedCompany" type="button" class="mail-unlink-company" :disabled="busy" aria-label="Usuń przypisanie firmy" title="Usuń przypisanie tylko tego adresu e-mail do firmy" @click="removeCompany"><Building2 :size="16" /> Usuń powiązanie</button><button type="button" :disabled="busy" @click="companyEditor = null">Anuluj</button><button class="primary" title="Zapisz przypisanie nadawcy do firmy" :disabled="busy"><Building2 :size="17" /> Zapisz przypisanie</button></footer></form></div>
    <div v-if="composer" class="mail-modal"><form class="mail-dialog compose-dialog" role="dialog" aria-modal="true" aria-labelledby="compose-title" @submit.prevent="send"><header><h2 id="compose-title">{{ composer.id ? 'Wiadomość robocza' : 'Nowa wiadomość' }}</h2><button type="button" class="mail-icon" :disabled="busy" aria-label="Zamknij wiadomość" @click="composer = null" title="Zamknij wiadomość"><X :size="20" /></button></header><p v-if="error" class="mail-error" role="alert">{{ error }}</p><label>Do<input v-model="composer.recipient" type="email" maxlength="254" required :disabled="busy" placeholder="adres@firma.pl" /></label><label>Temat<input v-model="composer.subject" maxlength="200" required :disabled="busy" /></label><label>Wiadomość<textarea v-model="composer.content" rows="12" maxlength="100000" required :disabled="busy" /></label><p v-if="!settings?.smtp.configured" class="ai-footnote">Wysyłanie wymaga konfiguracji SMTP na serwerze. Możesz zapisać szkic.</p><p class="ai-footnote">Przekazywanie kopiuje treść wiadomości. Wysyłanie załączników nie jest jeszcze dostępne.</p><footer><button type="button" :disabled="busy" title="Zapisz treść w folderze Robocze" @click="save"><FileText :size="17" /> Zapisz szkic</button><button class="primary" title="Wyślij wiadomość przez SMTP" :disabled="busy || !settings?.smtp.configured"><Send :size="17" />{{ busy ? 'Zapisywanie…' : 'Wyślij' }}</button></footer></form></div>
  </section>
</template>

<style scoped>
.client-mail { --mail-blue:#086cff; --mail-blue-soft:color-mix(in srgb,var(--mail-blue) 9%,var(--surface)); font-size:13px; color:var(--text); }
.mail-header { display:flex; justify-content:flex-end; gap:20px; align-items:center; margin:0 0 24px; flex-wrap:wrap; }
.mail-title { display:flex; gap:12px; align-items:center; }.mail-title h1 { font-size:25px; letter-spacing:-.8px; margin:0 0 4px; }.mail-title small { color:var(--muted); font-size:11px; }.mail-logo { display:flex; background:var(--mail-blue); color:white; padding:11px; border-radius:12px; box-shadow:0 5px 15px #086cff20; }
.mail-search { display:flex; flex-direction:row; flex:1; align-items:center; gap:10px; padding:4px 14px; min-width:230px; border-radius:15px; background:var(--surface-soft); color:var(--muted); }.mail-search input { border:0; background:transparent; font-size:13px; padding:11px 0; }
.mail-digest { display:flex; text-align:left; padding:12px 16px; background:var(--mail-blue-soft); border-color:color-mix(in srgb,var(--mail-blue) 15%,var(--border)); border-radius:15px; }.mail-digest svg { color:#8757ff; }.mail-digest span { display:grid; gap:6px; }.mail-digest small { color:var(--secondary); font-size:11px; }
.mail-icon { padding:7px; border:0; background:transparent; color:var(--secondary); border-radius:8px; }
.mail-filters { display:flex; flex-wrap:wrap; gap:12px; align-items:center; justify-content:space-between; background:var(--surface); border:1px solid var(--border); padding:13px; border-radius:16px; margin-bottom:14px; }.filter-buttons,.mail-tools { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }.filter-buttons button { font-size:12px; padding:9px 13px; border:1px solid transparent; background:var(--surface-soft); }.filter-buttons button.active { color:var(--mail-blue); background:color-mix(in srgb,var(--mail-blue) 16%,var(--surface)); border-color:color-mix(in srgb,var(--mail-blue) 25%,var(--surface)); }.filter-buttons .urgent { color:#e82643; background:#ff35430b; }.filter-buttons .reply { color:#e87d00; background:#ff8e0010; }.filter-buttons .payment { color:#00936c; background:#00a77f0b; }.filter-buttons button span { border-radius:50%; background:var(--surface); width:21px; height:21px; display:grid; place-items:center; font-size:11px; }.mail-tools select { padding:7px; border:0; background:transparent; font-size:12px; }
.mail-layout { display:grid; grid-template-columns:minmax(260px,.95fr) minmax(300px,1.2fr) minmax(235px,.72fr); min-height:650px; border:1px solid var(--border); border-radius:18px; background:var(--surface); overflow:hidden; box-shadow:0 5px 25px #18284904; }.mail-list-panel { display:flex; flex-direction:column; border-right:1px solid var(--border); min-width:0; }.mail-list-heading { display:flex; align-items:center; justify-content:space-between; gap:6px; padding:17px 14px; color:var(--secondary); font-weight:600; border-bottom:1px solid var(--border); }.mail-list-heading small { margin-left:6px; color:var(--muted); }.mail-list-heading > div { display:flex; gap:3px; }.mail-new { color:var(--mail-blue); border:0; background:var(--mail-blue-soft); padding:8px 10px; font-size:12px; }.mail-message-list { flex:1; overflow-y:auto; max-height:650px; padding:5px; }.mail-row { display:flex; align-items:center; gap:5px; padding:16px 10px; border-bottom:1px solid var(--border); min-height:101px; border-radius:8px; }.mail-row.selected { background:var(--mail-blue-soft); box-shadow:inset 3px 0 #80afff; }.mail-row-open { display:flex; min-width:0; flex:1; gap:12px; padding:0; border:0; background:transparent; text-align:left; justify-content:flex-start; }.mail-avatar { display:grid; place-items:center; flex-shrink:0; width:42px; height:42px; border-radius:50%; font-size:16px; font-weight:600; }.tone-0 { background:#d6e5ff; color:#086cff; }.tone-1 { background:#f3e4bd; color:#665125; }.tone-2 { background:#e7d7ff; color:#7137be; }.tone-3 { background:#cff0eb; color:#16877c; }.tone-4 { background:#f5d8ec; color:#a0408f; }.mail-row-text { display:flex; flex-direction:column; gap:5px; overflow:hidden; }.mail-row-text strong { font-size:13px; font-weight:500; }.mail-row.unread strong { font-weight:700; }.mail-row.unread .mail-row-text strong::before { content:''; display:inline-block; width:6px; height:6px; border-radius:50%; margin-right:6px; background:var(--mail-blue); }.mail-row-text span { font-size:12px; }.mail-row-text small { font-size:11px; color:var(--secondary); }.mail-row-text > * { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }.mail-row-meta { display:flex; flex-direction:column; gap:6px; align-items:flex-end; flex-shrink:0; max-width:88px; }.mail-row-meta time { font-size:10px; color:var(--muted); }.star { padding:2px; }.starred { color:#eeab24; }.starred svg { fill:#eeab24; }.mail-tag { display:inline-block; white-space:nowrap; border-radius:6px; padding:5px 8px; font-size:10px; background:var(--surface-soft); }.mail-tag.urgent { background:#ffe3e8; color:#eb2342; }.mail-tag.reply { background:#fff0dd; color:#d47b00; }.mail-tag.payment { background:#dff5ee; color:#008768; }.mail-tag.info { background:#e0efff; color:#0874d9; }.mail-list-empty { padding:55px 20px; text-align:center; color:var(--muted); }.mail-list-empty h2 { margin:15px 0 10px; font-size:16px; color:var(--text); }.mail-list-empty p { line-height:1.7; }.mail-list-empty svg { color:var(--mail-blue); }
.mail-reader { display:flex; flex-direction:column; min-width:0; }.mail-reader-toolbar { display:flex; align-items:center; gap:4px; border-bottom:1px solid var(--border); padding:17px 15px; }.mail-reader-toolbar button { border:0; background:transparent; color:var(--secondary); padding:8px; font-size:12px; }.mail-reader-content { flex:1; padding:24px; }.mail-subject { display:flex; align-items:center; flex-wrap:wrap; gap:12px; margin-bottom:30px; }.mail-subject h2 { font-size:23px; line-height:1.35; letter-spacing:-.6px; margin:0; overflow-wrap:anywhere; }.mail-sender { display:flex; gap:12px; align-items:center; margin-bottom:35px; flex-wrap:wrap; }.mail-sender > div { display:flex; flex:1; flex-direction:column; gap:5px; min-width:0; overflow-wrap:anywhere; }.mail-sender small { color:var(--secondary); font-size:11px; }.mail-sender time { font-size:10px; color:var(--muted); }.mail-body { white-space:pre-wrap; line-height:1.85; font-size:14px; overflow-wrap:anywhere; min-height:180px; }.mail-attachments { margin-top:30px; padding-top:18px; border-top:1px solid var(--border); display:flex; flex-wrap:wrap; gap:9px; }.mail-attachments h3 { width:100%; font-size:12px; margin:0 0 5px; }.mail-attachments button { padding:12px; flex:1; min-width:170px; text-align:left; justify-content:flex-start; font-size:11px; }.attachment-icon { color:var(--mail-blue); }.mail-attachments button > span:nth-child(2) { flex:1; overflow-wrap:anywhere; }.mail-attachments small { display:block; color:var(--muted); margin-top:5px; }.mail-message-options { display:flex; flex-wrap:wrap; align-items:end; gap:10px; padding-top:25px; }.mail-message-options label { gap:6px; font-size:10px; color:var(--muted); }.mail-message-options select,.mail-message-options button { padding:7px; font-size:10px; }.mail-reader-empty { margin:auto; padding:60px 24px; text-align:center; }.mail-reader-empty > span { display:inline-flex; padding:25px; color:var(--mail-blue); background:var(--mail-blue-soft); border-radius:25px; margin-bottom:25px; }.mail-reader-empty h2 { font-size:18px; margin-bottom:12px; }.mail-reader-empty p { line-height:1.9; color:var(--secondary); font-size:12px; margin-bottom:25px; }
.mail-ai { padding:22px 16px; background:linear-gradient(150deg,color-mix(in srgb,#9765ff 6%,var(--surface)),var(--surface) 45%); border-left:1px solid var(--border); }.ai-card { background:var(--surface-soft); border-radius:13px; padding:16px 14px; margin-bottom:9px; }.ai-card h3 { display:flex; gap:8px; align-items:center; font-size:12px; margin:0 0 12px; flex-wrap:wrap; }.ai-card h3 svg { color:var(--mail-blue); }.ai-card p,.ai-card li { font-size:12px; line-height:1.75; margin:0; overflow-wrap:anywhere; }.ai-card ul { padding-left:20px; margin:0; }.priority-card { background:color-mix(in srgb,#ff738b 5%,var(--surface)); }.priority-card h3 { margin:0; }.priority-card svg { color:#ef344e !important; }.ai-reply { white-space:pre-wrap; color:var(--secondary); background:var(--surface); padding:12px; border-radius:9px; margin-bottom:12px !important; }.ai-action { color:var(--mail-blue); background:var(--surface); border-color:#9ebfff; width:100%; font-size:12px; padding:12px 8px; }.ai-attachment { display:inline-block; font-size:10px; background:var(--surface); padding:6px; border-radius:6px; margin:3px; overflow-wrap:anywhere; max-width:100%; }.ai-intro { padding:40px 10px 30px; text-align:center; }.ai-orb { display:inline-flex; padding:20px; border-radius:50%; color:#8351eb; background:linear-gradient(135deg,#e4edff,#f7e6ff); }.ai-intro h3 { font-size:19px; line-height:1.45; font-weight:600; }.ai-intro p { font-size:12px; line-height:1.8; color:var(--secondary); }.ai-footnote { display:block; color:var(--muted); font-size:10px; line-height:1.7; margin:12px 0 0; }
.mail-error,.mail-notice { border-radius:10px; padding:12px 16px; font-size:12px; }.mail-error { color:var(--theme-danger,#ba253b); background:color-mix(in srgb,#ff637d 10%,var(--surface)); }.mail-notice { color:var(--success); background:var(--success-soft); }.mail-modal { position:fixed; inset:0; z-index:100; background:#13213966; backdrop-filter:blur(5px); display:flex; align-items:center; justify-content:center; padding:24px; }.mail-dialog { width:min(600px,100%); max-height:90dvh; overflow:auto; background:var(--surface); border:1px solid var(--border); border-radius:18px; padding:26px; box-shadow:0 25px 80px #0003; }.mail-dialog header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }.mail-dialog header h2 { margin:0; }.mail-dialog h3 { font-size:13px; margin-top:24px; }.mail-dialog p { line-height:1.7; }.compose-dialog { gap:14px; }.compose-dialog label { gap:6px; font-size:12px; }.compose-dialog footer { display:flex; justify-content:flex-end; gap:10px; }.mobile-back { display:none; }
.tiles .mail-row { flex-direction:column; align-items:stretch; margin:6px; border:1px solid var(--border); }.tiles .mail-row-meta { flex-direction:row; align-items:center; max-width:none; justify-content:flex-end; }
.client-mail,.mail-ai,.filter-buttons,.mail-tools,.mail-digest { min-width:0; }
.mail-digest > span { min-width:0; }
.mail-digest svg { flex-shrink:0; }
@media(max-width:1250px) { .mail-layout { grid-template-columns:minmax(240px,.8fr) minmax(280px,1fr); }.mail-ai { grid-column:1 / -1; border-left:0; border-top:1px solid var(--border); }.ai-intro { padding:10px; }.ai-intro h3 br { display:none; }.mail-digest { margin-left:auto; }.mail-reader-content { padding:20px; } }
@media(max-width:650px) { .mail-header { gap:12px; }.mail-title { flex:1; }.mail-title h1 { font-size:22px; }.mail-search { order:3; flex-basis:100%; }.mail-digest { order:4; width:100%; }.mail-header > .mail-icon { order:2; }.mail-filters { padding:9px; }.filter-buttons { flex-wrap:nowrap; overflow-x:auto; width:100%; padding-bottom:4px; }.filter-buttons button { flex-shrink:0; }.mail-tools { margin-left:auto; }.mail-layout { grid-template-columns:1fr; min-height:500px; }.mail-reader { display:none; }.mail-list-panel { border:0; }.message-open .mail-list-panel { display:none; }.message-open .mail-reader { display:flex; }.mobile-back { display:inline-flex; }.mail-ai { grid-column:auto; }.mail-reader-toolbar { padding:12px; }.mail-subject h2 { font-size:21px; }.mail-modal { padding:10px; }.mail-dialog { padding:20px; }.mail-message-list { max-height:550px; } }

.mail-group { border:1px solid var(--border); border-radius:14px; background:var(--surface); overflow:hidden; margin-bottom:12px; }
.mail-group > summary { display:flex; align-items:center; gap:10px; padding:16px 13px; cursor:pointer; list-style:none; font-size:14px; font-weight:600; }
.mail-group > summary::-webkit-details-marker { display:none; }
.mail-group > summary > svg:first-child { color:var(--mail-blue); flex-shrink:0; }
.mail-group.ai-group > summary > svg:first-child { color:#8555ff; }
.mail-group > summary:focus-visible { outline:2px solid var(--mail-blue); outline-offset:-3px; border-radius:12px; }
.group-chevron { margin-left:auto; transform:rotate(-90deg); transition:transform .15s; color:var(--muted); }
.mail-group[open] > summary { border-bottom:1px solid var(--border); }
.mail-group[open] > summary .group-chevron { transform:rotate(90deg); }
.mail-group-content { padding:13px; }
.mail-group .mail-filters { display:grid; gap:16px; padding:0; margin:0 0 14px; border:0; border-radius:0; }
.mail-group .filter-buttons { display:grid; grid-template-columns:1fr; gap:6px; overflow:visible; padding:0; }
.mail-group .filter-buttons button { justify-content:flex-start; width:100%; text-align:left; }
.mail-group .filter-buttons button span { margin-left:auto; }
.mail-group .mail-tools { margin:0; width:100%; flex-wrap:nowrap; gap:4px; padding-top:12px; border-top:1px solid var(--border); }
.mail-group .mail-tools select { flex:1; min-width:0; }
.mail-account-settings { width:100%; justify-content:flex-start; padding:10px; font-size:12px; }
.mail-group .ai-intro { padding:24px 0; }

.mail-search-fields { display:grid; gap:13px; }
.mail-search-fields label { display:grid; gap:7px; font-size:12px; color:var(--secondary); }
.mail-search-fields input { width:100%; font-size:12px; padding:10px; background:var(--surface-soft); }
.mail-clear-search { width:100%; font-size:12px; padding:10px 6px; }

.mail-layout { min-height:calc(100dvh - 136px); }
.mail-group .mail-message-options { display:grid; gap:12px; align-items:stretch; padding:13px; }
.mail-group .mail-message-options label { display:grid; gap:7px; font-size:12px; }
.mail-group .mail-message-options select { width:100%; font-size:12px; padding:9px; }
.mail-group .mail-message-options button { justify-content:flex-start; text-align:left; font-size:12px; padding:10px; }
.mail-sender { margin-bottom:24px; align-items:flex-start; }
.mail-sender-address { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.mail-sender-address strong { overflow-wrap:anywhere; }
.mail-sender-address button { font-size:11px; padding:6px 8px; }
.mail-company { color:var(--mail-blue); background:var(--mail-blue-soft); }
.company-dialog .mail-unlink-company { margin-right:auto; color:var(--theme-danger,#ba253b); }
.mail-safe,.mail-blocked { display:inline-flex; align-items:center; gap:5px; font-size:11px; }
.mail-safe { color:var(--success); }.mail-blocked { color:var(--theme-danger,#ba253b); }
.mail-government { display:grid; gap:5px; margin:7px 0; padding:10px; border:1px solid color-mix(in srgb,var(--mail-blue) 20%,var(--border)); border-radius:10px; background:var(--mail-blue-soft); }.mail-government > span { display:flex; align-items:center; flex-wrap:wrap; gap:6px; color:var(--mail-blue); font-size:11px; }.mail-government strong { overflow-wrap:anywhere; }.mail-government > small { font-size:10px; line-height:1.6; color:var(--secondary); }
.company-dialog { display:grid; gap:14px; }.company-dialog header { margin:0; gap:10px; }
.company-dialog h2 { font-size:20px; }.company-dialog label { display:grid; gap:7px; font-size:12px; }
.company-dialog footer { display:flex; justify-content:flex-end; gap:10px; flex-wrap:wrap; }
.company-address { overflow-wrap:anywhere; margin:0; color:var(--secondary); }
.mail-category { display:inline-flex; border-radius:6px; padding:5px 8px; font-size:10px; color:var(--mail-blue); background:var(--mail-blue-soft); }
.mail-category.spam { color:var(--theme-danger,#ba253b); background:color-mix(in srgb,#ff637d 10%,var(--surface)); }
.mail-category.invoice,.mail-category.payment { color:var(--success); background:var(--success-soft); }
.mail-category-filter { display:grid; gap:7px; font-size:12px; color:var(--secondary); margin-bottom:14px; }
.mail-category-filter select { width:100%; padding:9px; }
.mail-attachments-heading { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; width:100%; margin-bottom:5px; }
.mail-attachments .mail-attachments-heading h3 { width:auto; margin:0; }.mail-attachments .mail-attachments-heading button { flex:0 1 auto; min-width:0; padding:8px; }
.mail-attachment-card { display:flex; flex-direction:column; flex:1; min-width:min(220px,100%); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
.mail-attachments .mail-attachment-card button { flex:0 1 auto; width:100%; min-width:0; border:0; border-radius:0; }
.mail-attachments .mail-attachment-card .mail-save-attachment { border-top:1px solid var(--border); color:var(--mail-blue); background:var(--mail-blue-soft); padding:9px 12px; }
.mail-drive-dialog { display:grid; gap:15px; }.mail-drive-dialog header { margin:0; gap:10px; }.mail-drive-dialog h2 { display:flex; align-items:center; gap:9px; font-size:19px; }
.mail-drive-dialog > label { display:grid; gap:7px; font-size:12px; }.mail-drive-dialog fieldset { margin:0; padding:12px; border:1px solid var(--border); border-radius:10px; min-width:0; }.mail-drive-dialog legend { padding:0 5px; font-size:12px; }
.mail-drive-file { display:flex; flex-direction:row; align-items:center; gap:10px; padding:8px 0; }.mail-drive-file input { width:16px; height:16px; flex-shrink:0; }.mail-drive-file span { min-width:0; overflow-wrap:anywhere; font-size:12px; }.mail-drive-file small { display:block; font-size:10px; color:var(--secondary); margin-top:4px; }
.mail-drive-new { justify-self:start; font-size:12px; }.mail-drive-dialog footer { display:flex; justify-content:flex-end; gap:10px; flex-wrap:wrap; }.mail-drive-saved { font-size:11px; line-height:1.8; padding-left:20px; overflow-wrap:anywhere; }
.mail-title-line { display:flex; align-items:center; gap:10px; }.mail-title-line h1 { margin:0; }.mail-title-line button { padding:6px; border:0; background:transparent; color:var(--secondary); border-radius:8px; }
.mail-folder-title { display:flex; align-items:center; gap:6px; }.mail-folder-title small { margin:0; }
.mail-inline-label { display:flex; flex-direction:row; flex-wrap:wrap; align-items:center; gap:8px; margin:8px 0 3px; font-size:11px; color:var(--secondary); }
.mail-label-trigger { padding:5px 9px; gap:8px; font-size:11px; background:var(--surface-soft); border-color:transparent; border-radius:7px; }.mail-label-trigger > svg { transform:rotate(-90deg); }.mail-label-trigger.urgent { color:var(--theme-danger,#ba253b); background:color-mix(in srgb,#ff637d 12%,var(--surface)); }.mail-label-trigger.invoice { color:var(--success); background:var(--success-soft); }.mail-label-trigger.offer { color:var(--accent); background:var(--accent-soft); }
.mail-row-label { border:0; cursor:pointer; }.mail-row-label:hover { box-shadow:0 0 0 1px var(--accent); }.mail-row-label.none { color:var(--muted); }
.mail-sender-symbol { display:grid; place-items:center; position:relative; flex-shrink:0; width:45px; height:45px; border-radius:15px; color:var(--sender-color,var(--secondary)); background:linear-gradient(145deg,color-mix(in srgb,var(--sender-color,var(--secondary)) 17%,var(--surface)),color-mix(in srgb,var(--sender-color,var(--secondary)) 5%,var(--surface))); border:1px solid color-mix(in srgb,var(--sender-color,var(--secondary)) 22%,var(--border)); box-shadow:0 3px 7px color-mix(in srgb,var(--sender-color,var(--secondary)) 8%,transparent); }.mail-sender-symbol::after { content:''; position:absolute; bottom:-2px; right:-2px; width:9px; height:9px; border-radius:50%; border:2px solid var(--surface); background:var(--sender-color,var(--secondary)); }.sender-company { --sender-color:#138b80; }.sender-government { --sender-color:#2879dd; }.sender-marketing { --sender-color:#9560ce; }.sender-notification { --sender-color:#b37a12; }.sender-phishing,.sender-spam { --sender-color:#d03e5c; }.sender-sent,.sender-draft { --sender-color:var(--accent); }
.mail-row-text .mail-row-affiliations { display:flex; flex-wrap:wrap; gap:5px; overflow:visible; white-space:normal; }.mail-row-affiliations > span { display:inline-flex; align-items:center; gap:4px; min-width:0; max-width:100%; padding:4px 6px; border-radius:5px; font-size:10px; line-height:1.3; }.mail-row-affiliations > span > svg { flex-shrink:0; }.mail-row-affiliations > span > span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:10px; }.mail-row-company { background:var(--accent-soft); color:var(--accent); }.mail-row-government { background:var(--mail-blue-soft); color:var(--mail-blue); border:1px solid color-mix(in srgb,var(--mail-blue) 25%,var(--border)); }
.mail-label-popup { position:fixed; margin:0; width:200px; padding:6px; border:1px solid var(--border); border-radius:12px; background:var(--surface); color:var(--text); box-shadow:0 10px 35px #15213d25; }
.mail-label-popup button { display:flex; width:100%; justify-content:flex-start; gap:10px; border:0; padding:10px; font-size:12px; border-radius:7px; background:transparent; }.mail-label-popup button:hover,.mail-label-popup button[aria-pressed="true"] { background:var(--accent-soft); }.mail-label-dot { width:8px; height:8px; border-radius:50%; background:var(--muted); flex-shrink:0; }.mail-label-dot.urgent { background:#ed4764; }.mail-label-dot.invoice { background:#17a383; }.mail-label-dot.offer { background:#a27aef; }.mail-label-check { margin-left:auto; color:var(--accent); }
.mail-tag.invoice { color:#13775b; background:#dff5ee; }.mail-tag.offer { color:#915a0b; background:#fff0dd; }
.mail-spam-button { color:var(--theme-danger,#ba253b); }
.mail-phishing-warning { display:flex; align-items:flex-start; gap:10px; padding:13px; margin:0 0 20px; border:1px solid color-mix(in srgb,#ed4764 30%,var(--border)); border-radius:10px; color:var(--theme-danger,#ba253b); background:color-mix(in srgb,#ed4764 8%,var(--surface)); font-size:12px; line-height:1.7; }.mail-phishing-warning svg { flex-shrink:0; margin-top:2px; }
.mail-reader-toolbar { flex-wrap:wrap; }.mail-reader-toolbar > button { white-space:nowrap; }.mail-reader-toolbar .mail-spam-button { color:var(--theme-danger,#ba253b); }
.mail-side-panel { background:var(--surface-soft); display:flex; flex-direction:column; gap:22px; }
.mail-side-panel > * { flex-shrink:0; }
.mail-side-panel h2 { display:flex; align-items:center; gap:8px; font-size:13px; margin:0 0 7px; }.mail-side-panel h2 small { margin-left:auto; color:var(--muted); }
.mail-side-attachments .mail-attachments { display:grid; gap:10px; margin:0; padding:6px 0 0; border:0; }.mail-side-attachments .mail-attachment-card { min-width:0; flex-direction:row; align-items:center; gap:6px; padding:10px; background:var(--surface); }.mail-side-attachments .mail-save-all { min-width:0; font-size:11px; }
.mail-file-description { display:flex; align-items:center; gap:8px; min-width:0; flex:1; }.mail-file-description > svg { flex-shrink:0; }.mail-file-description > span { min-width:0; overflow-wrap:anywhere; font-size:11px; }.mail-file-description small { display:block; color:var(--muted); margin-top:5px; font-size:10px; }
.mail-file-actions { display:flex; align-items:center; gap:2px; flex-shrink:0; }.mail-attachments .mail-file-actions button { width:32px; min-width:32px; height:34px; padding:6px; border-radius:7px; background:transparent; }.mail-attachments .mail-file-actions button:last-child { color:var(--mail-blue); }.mail-attachments .mail-file-actions button:hover { background:var(--accent-soft); }
.mail-side-empty { color:var(--secondary); font-size:12px; line-height:1.7; margin:0; }
.mail-time-range { display:flex; align-items:center; gap:4px; flex-wrap:wrap; padding:10px 12px; border-bottom:1px solid var(--border); flex-shrink:0; }.mail-time-range > span { font-size:10px; color:var(--secondary); margin-right:5px; }.mail-time-range button { padding:6px 9px; border:1px solid transparent; background:var(--surface-soft); color:var(--secondary); font-size:11px; border-radius:7px; }.mail-time-range button[aria-pressed="true"] { color:var(--accent); background:var(--accent-soft); border-color:color-mix(in srgb,var(--accent) 25%,var(--border)); }.mail-range-loading { margin-left:auto; color:var(--accent); animation:mail-range-spin 1s linear infinite; }@keyframes mail-range-spin { to { transform:rotate(360deg); } }@media(prefers-reduced-motion:reduce) { .mail-range-loading { animation:none; } }
@media (min-width:1251px) { .mail-layout { grid-template-columns:minmax(350px,1.2fr) minmax(320px,1.45fr) minmax(230px,.65fr); } }
@media (min-width:651px) and (max-width:1250px) { .mail-layout { grid-template-columns:minmax(300px,1fr) minmax(280px,1.15fr); } }
@media (min-width:651px) and (max-width:1250px) { .mail-side-panel { display:grid; grid-template-columns:1fr 1fr; align-items:start; }.mail-side-panel > .ai-group { grid-column:1 / -1; } }
@media (max-width:650px) { .mail-side-panel { display:none; }.message-open .mail-side-panel { display:flex; }.mail-list-heading { padding:12px 10px; }.mail-folder-title { gap:4px; } }
.mail-spam-notice { display:flex; align-items:center; gap:12px; }
.mail-spam-flight { position:relative; display:inline-block; width:82px; height:30px; flex-shrink:0; }
.mail-flying-envelope { position:absolute; right:0; top:5px; animation:mail-fly-to-spam .8s ease-in both; }
.mail-spam-destination { position:absolute; left:0; top:3px; animation:mail-spam-arrival .35s .7s ease-out both; }
@keyframes mail-fly-to-spam { 0% { transform:translateX(0) rotate(0); opacity:1; } 45% { transform:translate(-25px,-9px) rotate(-15deg); opacity:1; } 100% { transform:translateX(-58px) scale(.25); opacity:0; } }
@keyframes mail-spam-arrival { 0%,100% { transform:scale(1); } 50% { transform:scale(1.25); } }
@media (prefers-reduced-motion:reduce) { .mail-flying-envelope { animation:none; display:none; }.mail-spam-destination { animation:none; } }
@media (min-width:1251px) {
  .client-mail { display:flex; flex-direction:column; flex:1; min-height:0; }
  .mail-layout { flex:1; min-height:0; grid-template-rows:minmax(0,1fr); }
  .mail-list-panel, .mail-reader { min-height:0; overflow:hidden; }
  .mail-message-list { min-height:0; max-height:none; }
  .mail-reader-content { min-height:0; overflow-y:auto; }
  .mail-list-heading, .mail-reader-toolbar { flex-shrink:0; }
  .mail-ai { min-height:0; overflow-y:auto; }
}
</style>
