<script setup>
import { computed, onMounted, ref } from 'vue'
import MailSettings from './MailSettings.vue'
import { Mail, Search, Sparkles, Settings, Plus, Upload, RefreshCw, Star, Reply, Forward, Trash2, Archive, Paperclip, Inbox, Send, FileText, ShieldAlert, X, Download, ChevronLeft, List, LayoutGrid, CheckSquare, Lightbulb, AlertCircle, Pin } from 'lucide-vue-next'
const props = defineProps({ api: Function })
const messages = ref([]), selectedId = ref(null), folder = ref('inbox'), filter = ref('all'), search = ref({ email: '', subject: '', content: '', filename: '' }), sort = ref('newest'), grid = ref(false)
const headerSearch = ref('')
const busy = ref(false), error = ref(''), notice = ref(''), settings = ref(null), showSettings = ref(false), composer = ref(null), analysis = ref({}), aiBusy = ref(false), importInput = ref(null)
const folders = [
  { id: 'inbox', label: 'Odebrane', icon: Inbox }, { id: 'sent', label: 'Wysłane', icon: Send },
  { id: 'drafts', label: 'Robocze', icon: FileText }, { id: 'archive', label: 'Archiwum', icon: Archive },
  { id: 'spam', label: 'Spam', icon: ShieldAlert }, { id: 'trash', label: 'Śmieci', icon: Trash2 }
]
const filters = [{ id: 'all', label: 'Wszystkie' }, { id: 'unread', label: 'Nieprzeczytane' }, { id: 'urgent', label: 'Pilne' }, { id: 'reply', label: 'Do odpowiedzi' }, { id: 'payment', label: 'Do zapłaty' }, { id: 'attachments', label: 'Załączniki' }]
const labels = { urgent: 'Pilne', reply: 'Do odpowiedzi', payment: 'Do zapłaty', info: 'Informacja' }
const selected = computed(() => messages.value.find(m => m.id === selectedId.value))
const currentAnalysis = computed(() => analysis.value[selectedId.value])
const inbox = computed(() => messages.value.filter(m => m.folder === 'inbox'))
const unread = computed(() => inbox.value.filter(m => m.unread).length)
const matches = (value, query) => (value || '').toLocaleLowerCase('pl').includes(query.trim().toLocaleLowerCase('pl'))
function clearSearch() { search.value = { email: '', subject: '', content: '', filename: '' } }
const filtered = computed(() => messages.value.filter(m => m.folder === folder.value)
  .filter(m => filter.value === 'all' || (filter.value === 'unread' ? m.unread : filter.value === 'attachments' ? m.attachments.length : m.label === filter.value))
  .filter(m => !headerSearch.value.trim() || [m.sender_name, m.sender_email, m.recipient, m.subject, m.content, ...m.attachments.map(part => part.name)].some(value => matches(value, headerSearch.value)))
  .filter(m => (!search.value.email.trim() || [m.sender_email, m.recipient].some(value => matches(value, search.value.email)))
    && matches(m.subject, search.value.subject)
    && matches(m.content, search.value.content)
    && (!search.value.filename.trim() || m.attachments.some(part => matches(part.name, search.value.filename))))
  .sort((a, b) => (sort.value === 'newest' ? -1 : 1) * (Date.parse(a.created_at) - Date.parse(b.created_at))))
const initials = m => (m.sender_name || m.sender_email || '?').split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase()
const date = value => new Date(value).toLocaleDateString('pl-PL', { day: 'numeric', month: 'short' })
const fullDate = value => new Date(value).toLocaleString('pl-PL', { dateStyle: 'medium', timeStyle: 'short' })
const size = value => value < 1024 ? `${value} B` : value < 1024 * 1024 ? `${Math.round(value / 1024)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
function replace(message) { messages.value = [message, ...messages.value.filter(m => m.id !== message.id)] }
async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { return await action() } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function load() {
  const result = await Promise.all([props.api('/client-mail'), props.api('/client-mail/settings')])
  messages.value = result[0]; settings.value = result[1]
  if (!selected.value) selectedId.value = null
}
async function refresh() {
  await load()
  if (!settings.value.account.imap.enabled) {
    notice.value = 'Aby odbierać wiadomości, włącz IMAP w ustawieniach poczty.'
    return
  }
  const result = await props.api('/client-mail/sync', 'POST')
  await load()
  notice.value = `Pobrano wiadomości: ${result.imported}.` + (result.remaining ? ` Pozostało: ${result.remaining}. Odśwież ponownie.` : '') + (result.skipped ? ` Pominięto zbyt duże lub niepoprawne wiadomości: ${result.skipped}.` : '')
}
async function patch(message, changes) {
  const result = await props.api(`/client-mail/${message.id}`, 'PATCH', { version: message.version, ...changes })
  replace(result); return result
}
function changeFolder(id) { folder.value = id; selectedId.value = null; filter.value = 'all' }
async function open(message) {
  if (busy.value) return
  selectedId.value = message.id
  if (message.folder === 'drafts') { compose(message); return }
  if (message.unread) await run(() => patch(message, { unread: false }))
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
    replace(message); changeFolder('inbox'); selectedId.value = message.id; notice.value = 'Wiadomość została zaimportowana.'
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
  await run(async () => {
    const response = await fetch(`/api/client-mail/${selected.value.id}/attachments/${part.id}`, { credentials: 'same-origin' })
    if (!response.ok) throw new Error('Nie udało się pobrać załącznika.')
    const url = URL.createObjectURL(await response.blob()), a = document.createElement('a')
    a.href = url; a.download = part.name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
}
onMounted(() => run(load))
</script>

<template>
  <section class="client-mail" aria-label="Poczta Klienta">
    <div class="mail-heading">
      <Teleport to="#workspace-title"><div class="mail-title"><span class="mail-logo"><Mail :size="24" /></span><div><h1>Poczta Klienta</h1><small>Twoja korespondencja, uporządkowana.</small></div></div></Teleport>
      <Teleport to="#workspace-search"><label class="mail-search"><Search :size="19" /><input v-model="headerSearch" type="search" aria-label="Szukaj w wiadomościach po temacie, adresie e-mail, treści lub nazwie pliku" placeholder="Szukaj w wiadomościach: temat, e-mail, treść, pliki…" /></label></Teleport>
    </div>
    <p v-if="error" class="mail-error" role="alert">{{ error }}</p><p v-if="notice" class="mail-notice" role="status">{{ notice }}</p>
    <div class="mail-layout" :class="{ 'message-open': selected }">
      <aside class="mail-list-panel">
        <div class="mail-list-heading"><span>{{ folders.find(f => f.id === folder)?.label }} <small>{{ filtered.length }}</small></span><div><button class="mail-icon" :disabled="busy" aria-label="Importuj wiadomość .eml" @click="importInput.click()"><Upload :size="17" /></button><button class="mail-new" :disabled="busy" @click="compose()"><Plus :size="16" /> Napisz</button></div></div>
        <input ref="importInput" type="file" accept=".eml" hidden aria-label="Plik wiadomości .eml" @change="importMail" />
        <div class="mail-message-list" :class="{ tiles: grid }" aria-label="Lista wiadomości">
          <article v-for="(message, index) in filtered" :key="message.id" class="mail-row" :class="{ selected: selectedId === message.id, unread: message.unread }">
            <button class="mail-row-open" :disabled="busy" @click="open(message)"><span class="mail-avatar" :class="`tone-${index % 5}`">{{ initials(message) }}</span><span class="mail-row-text"><strong>{{ folder === 'sent' || folder === 'drafts' ? message.recipient || 'Brak odbiorcy' : message.sender_name }}</strong><span>{{ message.subject || '(bez tematu)' }}</span><small>{{ message.content || 'Pusty szkic' }}</small></span></button>
            <div class="mail-row-meta"><time :datetime="message.created_at">{{ date(message.created_at) }}</time><button class="mail-icon star" :class="{ starred: message.starred }" :disabled="busy" :aria-label="message.starred ? 'Usuń gwiazdkę' : 'Oznacz gwiazdką'" :aria-pressed="!!message.starred" @click="run(() => patch(message, { starred: !message.starred }))"><Star :size="17" /></button><span v-if="message.label" class="mail-tag" :class="message.label">{{ labels[message.label] }}</span><Paperclip v-else-if="message.attachments.length" :size="14" /></div>
          </article>
          <div v-if="!filtered.length" class="mail-list-empty"><Inbox :size="35" /><h2>{{ busy ? 'Wczytywanie poczty…' : 'Brak wiadomości' }}</h2><p>{{ messages.length ? 'Zmień folder, filtr lub wyszukiwanie.' : 'Importuj wiadomość .eml lub napisz pierwszego maila.' }}</p><button v-if="!messages.length" :disabled="busy" @click="importInput.click()"><Upload :size="16" /> Importuj .eml</button></div>
        </div>
        <nav class="mail-folders" aria-label="Foldery poczty"><button v-for="item in folders" :key="item.id" :class="{ active: folder === item.id }" :aria-current="folder === item.id ? 'page' : undefined" @click="changeFolder(item.id)"><component :is="item.icon" :size="19" /><span>{{ item.label }}</span><small v-if="messages.filter(m => m.folder === item.id).length">{{ messages.filter(m => m.folder === item.id).length }}</small></button></nav>
      </aside>
      <section class="mail-reader" aria-label="Podgląd wiadomości">
        <template v-if="selected">
          <div class="mail-reader-toolbar"><button class="mobile-back mail-icon" aria-label="Wróć do listy" @click="selectedId = null"><ChevronLeft :size="18" /></button><button :disabled="busy" @click="compose(selected, 'reply')"><Reply :size="17" /><span>Odpowiedz</span></button><button :disabled="busy" @click="compose(selected, 'forward')"><Forward :size="17" /><span>Przekaż</span></button><button :disabled="busy" aria-label="Przenieś do śmieci" @click="run(() => patch(selected, { folder: 'trash' }))"><Trash2 :size="17" /></button><button :disabled="busy" aria-label="Archiwizuj" @click="run(() => patch(selected, { folder: 'archive' }))"><Archive :size="17" /></button></div>
          <div class="mail-reader-content"><div class="mail-subject"><h2>{{ selected.subject || '(bez tematu)' }}</h2><span v-if="selected.label" class="mail-tag" :class="selected.label">{{ labels[selected.label] }}</span></div>
          <div class="mail-sender"><span class="mail-avatar tone-0">{{ initials(selected) }}</span><div><strong>{{ selected.sender_name }}</strong><small>{{ selected.sender_email }}</small><small>Do: {{ selected.recipient || 'mnie' }}</small></div><time :datetime="selected.created_at">{{ fullDate(selected.created_at) }}</time></div>
          <div class="mail-body">{{ selected.content }}</div>
          <div v-if="selected.attachments.length" class="mail-attachments"><h3>{{ selected.attachments.length }} załączników</h3><button v-for="part in selected.attachments" :key="part.id" :disabled="busy" @click="download(part)"><span class="attachment-icon"><FileText :size="23" /></span><span>{{ part.name }}<small>{{ size(part.size) }}</small></span><Download :size="17" /></button></div>
          <div class="mail-message-options"><label>Etykieta<select :value="selected.label" :disabled="busy" @change="run(() => patch(selected, { label: $event.target.value }))"><option value="">Bez etykiety</option><option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</option></select></label><label>Folder<select :value="selected.folder" :disabled="busy || ['sent', 'drafts'].includes(selected.folder)" @change="run(() => patch(selected, { folder: $event.target.value }))"><option v-for="item in folders" :key="item.id" :value="item.id" :disabled="['sent','drafts'].includes(item.id)">{{ item.label }}</option></select></label><button :disabled="busy" @click="run(() => patch(selected, { unread: !selected.unread }))">{{ selected.unread ? 'Oznacz jako przeczytaną' : 'Oznacz jako nieprzeczytaną' }}</button></div>
          </div>
        </template>
        <div v-else class="mail-reader-empty"><span><Mail :size="42" /></span><h2>Miejsce na Twoją korespondencję</h2><p>Wybierz wiadomość, aby przeczytać jej treść,<br />pobrać załączniki i przygotować odpowiedź.</p><button class="primary" @click="compose()"><Plus :size="17" /> Nowa wiadomość</button></div>
      </section>
      <aside class="mail-ai" aria-label="Szukaj, ustawienia i analiza poczty">
        <details class="mail-group mail-search-group">
          <summary><Search :size="20" /><span>Szukaj</span><ChevronLeft class="group-chevron" :size="17" /></summary>
          <div class="mail-group-content mail-search-fields">
            <label>Po adresie e-mail:<input v-model="search.email" type="search" aria-label="Szukaj po adresie e-mail" placeholder="Adres nadawcy lub odbiorcy" /></label>
            <label>Po temacie:<input v-model="search.subject" type="search" aria-label="Szukaj po temacie" placeholder="Fragment tematu" /></label>
            <label>Po treści:<input v-model="search.content" type="search" aria-label="Szukaj po treści" placeholder="Fragment treści wiadomości" /></label>
            <label>Po nazwie pliku:<input v-model="search.filename" type="search" aria-label="Szukaj po nazwie pliku" placeholder="Nazwa załącznika" /></label>
            <button class="mail-clear-search" :disabled="!Object.values(search).some(value => value.trim())" @click="clearSearch"><X :size="16" /> Wyczyść wyszukiwanie</button>
          </div>
        </details>
        <details class="mail-group">
          <summary><Settings :size="20" /><span>Ustawienia</span><ChevronLeft class="group-chevron" :size="17" /></summary>
          <div class="mail-group-content">
            <div class="mail-filters">
      <div class="filter-buttons"><button v-for="item in filters" :key="item.id" :class="[item.id, { active: filter === item.id }]" :aria-pressed="filter === item.id" @click="filter = item.id"><Paperclip v-if="item.id === 'attachments'" :size="16" />{{ item.label }}<span v-if="['urgent','reply','payment'].includes(item.id)">{{ messages.filter(m => m.folder === folder && m.label === item.id).length }}</span></button></div>
      <div class="mail-tools"><select v-model="sort" aria-label="Kolejność wiadomości"><option value="newest">Najnowsze</option><option value="oldest">Najstarsze</option></select><button class="mail-icon" :disabled="busy" aria-label="Odśwież pocztę" @click="run(refresh)"><RefreshCw :size="17" /></button><button class="mail-icon" :aria-label="grid ? 'Widok listy' : 'Widok kafelków'" :aria-pressed="grid" @click="grid = !grid"><LayoutGrid v-if="!grid" :size="17" /><List v-else :size="17" /></button></div>
    </div>
            <button class="mail-account-settings" @click="showSettings = true"><Settings :size="17" /> Ustawienia konta pocztowego</button>
          </div>
        </details>
        <details class="mail-group ai-group">
          <summary><Sparkles :size="20" /><span>Analiza AI</span><ChevronLeft class="group-chevron" :size="17" /></summary>
          <div class="mail-group-content"><template v-if="currentAnalysis"><div class="ai-card"><h3><Pin :size="17" /> Podsumowanie</h3><p>{{ currentAnalysis.summary }}</p></div><div class="ai-card priority-card"><h3><AlertCircle :size="17" /> Priorytet <span class="mail-tag" :class="currentAnalysis.priority === 'high' ? 'urgent' : 'info'">{{ currentAnalysis.priority === 'high' ? 'Wysoki' : 'Normalny' }}</span></h3></div><div class="ai-card"><h3><CheckSquare :size="17" /> Wykryte zadania</h3><ul v-if="currentAnalysis.tasks.length"><li v-for="task in currentAnalysis.tasks" :key="task">{{ task }}</li></ul><p v-else>Nie wykryto zadań.</p></div><div v-if="selected?.attachments.length" class="ai-card"><h3><Paperclip :size="17" /> Załączniki</h3><span v-for="part in selected.attachments" :key="part.id" class="ai-attachment">{{ part.name }}</span></div><div class="ai-card"><h3><Lightbulb :size="18" /> Proponowana odpowiedź</h3><p class="ai-reply">{{ currentAnalysis.reply }}</p><button class="ai-action" :disabled="busy" @click="useReply"><Reply :size="17" /> Użyj odpowiedzi</button></div></template>
        <div v-else class="ai-intro"><span class="ai-orb"><Sparkles :size="30" /></span><h3>Mniej czytania.<br />Więcej konkretów.</h3><p>Podsumowanie, priorytet, zadania i propozycja odpowiedzi w jednym miejscu.</p></div>
        <button class="ai-action" :disabled="!selected || aiBusy || !settings?.ai.available" @click="analyze"><Sparkles :size="17" />{{ aiBusy ? 'Analizowanie…' : currentAnalysis ? 'Analizuj ponownie' : 'Przeanalizuj wiadomość' }}</button><small class="ai-footnote">{{ settings && !settings.ai.available ? settings.ai.message : 'Analiza przesyła treść wybranej wiadomości do AI. Sprawdź propozycję przed wysłaniem.' }}</small>
          </div>
        </details>
      </aside>
    </div>
    <MailSettings v-if="showSettings" :api="api" :initial="settings" @close="showSettings = false" @saved="settings = $event" />
    <div v-if="composer" class="mail-modal"><form class="mail-dialog compose-dialog" role="dialog" aria-modal="true" aria-labelledby="compose-title" @submit.prevent="send"><header><h2 id="compose-title">{{ composer.id ? 'Wiadomość robocza' : 'Nowa wiadomość' }}</h2><button type="button" class="mail-icon" :disabled="busy" aria-label="Zamknij wiadomość" @click="composer = null"><X :size="20" /></button></header><p v-if="error" class="mail-error" role="alert">{{ error }}</p><label>Do<input v-model="composer.recipient" type="email" maxlength="254" required :disabled="busy" placeholder="adres@firma.pl" /></label><label>Temat<input v-model="composer.subject" maxlength="200" required :disabled="busy" /></label><label>Wiadomość<textarea v-model="composer.content" rows="12" maxlength="100000" required :disabled="busy" /></label><p v-if="!settings?.smtp.configured" class="ai-footnote">Wysyłanie wymaga konfiguracji SMTP na serwerze. Możesz zapisać szkic.</p><p class="ai-footnote">Przekazywanie kopiuje treść wiadomości. Wysyłanie załączników nie jest jeszcze dostępne.</p><footer><button type="button" :disabled="busy" @click="save"><FileText :size="17" /> Zapisz szkic</button><button class="primary" :disabled="busy || !settings?.smtp.configured"><Send :size="17" />{{ busy ? 'Zapisywanie…' : 'Wyślij' }}</button></footer></form></div>
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
.mail-layout { display:grid; grid-template-columns:minmax(260px,.95fr) minmax(300px,1.2fr) minmax(235px,.72fr); min-height:650px; border:1px solid var(--border); border-radius:18px; background:var(--surface); overflow:hidden; box-shadow:0 5px 25px #18284904; }.mail-list-panel { display:flex; flex-direction:column; border-right:1px solid var(--border); min-width:0; }.mail-list-heading { display:flex; align-items:center; justify-content:space-between; gap:6px; padding:17px 14px; color:var(--secondary); font-weight:600; border-bottom:1px solid var(--border); }.mail-list-heading small { margin-left:6px; color:var(--muted); }.mail-list-heading > div { display:flex; gap:3px; }.mail-new { color:var(--mail-blue); border:0; background:var(--mail-blue-soft); padding:8px 10px; font-size:12px; }.mail-message-list { flex:1; overflow-y:auto; max-height:650px; padding:5px; }.mail-row { display:flex; align-items:center; gap:5px; padding:16px 10px; border-bottom:1px solid var(--border); min-height:101px; border-radius:8px; }.mail-row.selected { background:var(--mail-blue-soft); box-shadow:inset 3px 0 #80afff; }.mail-row-open { display:flex; min-width:0; flex:1; gap:12px; padding:0; border:0; background:transparent; text-align:left; justify-content:flex-start; }.mail-avatar { display:grid; place-items:center; flex-shrink:0; width:42px; height:42px; border-radius:50%; font-size:16px; font-weight:600; }.tone-0 { background:#d6e5ff; color:#086cff; }.tone-1 { background:#f3e4bd; color:#665125; }.tone-2 { background:#e7d7ff; color:#7137be; }.tone-3 { background:#cff0eb; color:#16877c; }.tone-4 { background:#f5d8ec; color:#a0408f; }.mail-row-text { display:flex; flex-direction:column; gap:5px; overflow:hidden; }.mail-row-text strong { font-size:13px; font-weight:500; }.mail-row.unread strong { font-weight:700; }.mail-row.unread .mail-row-text strong::before { content:''; display:inline-block; width:6px; height:6px; border-radius:50%; margin-right:6px; background:var(--mail-blue); }.mail-row-text span { font-size:12px; }.mail-row-text small { font-size:11px; color:var(--secondary); }.mail-row-text > * { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }.mail-row-meta { display:flex; flex-direction:column; gap:6px; align-items:flex-end; flex-shrink:0; max-width:88px; }.mail-row-meta time { font-size:10px; color:var(--muted); }.star { padding:2px; }.starred { color:#eeab24; }.starred svg { fill:#eeab24; }.mail-tag { display:inline-block; white-space:nowrap; border-radius:6px; padding:5px 8px; font-size:10px; background:var(--surface-soft); }.mail-tag.urgent { background:#ffe3e8; color:#eb2342; }.mail-tag.reply { background:#fff0dd; color:#d47b00; }.mail-tag.payment { background:#dff5ee; color:#008768; }.mail-tag.info { background:#e0efff; color:#0874d9; }.mail-list-empty { padding:55px 20px; text-align:center; color:var(--muted); }.mail-list-empty h2 { margin:15px 0 10px; font-size:16px; color:var(--text); }.mail-list-empty p { line-height:1.7; }.mail-list-empty svg { color:var(--mail-blue); }.mail-folders { display:grid; grid-template-columns:repeat(3,1fr); gap:4px; border-top:1px solid var(--border); padding:12px 8px; }.mail-folders button { position:relative; border:0; padding:10px 4px; flex-direction:column; font-size:10px; gap:6px; background:transparent; color:var(--secondary); }.mail-folders button.active { background:var(--mail-blue-soft); color:var(--mail-blue); }.mail-folders small { position:absolute; right:7px; top:6px; background:var(--mail-blue-soft); border-radius:20px; padding:2px 5px; font-size:9px; }
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
@media (min-width:1251px) {
  .client-mail { display:flex; flex-direction:column; flex:1; min-height:0; }
  .mail-layout { flex:1; min-height:0; grid-template-rows:minmax(0,1fr); }
  .mail-list-panel, .mail-reader { min-height:0; overflow:hidden; }
  .mail-message-list { min-height:0; max-height:none; }
  .mail-reader-content { min-height:0; overflow-y:auto; }
  .mail-list-heading, .mail-folders, .mail-reader-toolbar { flex-shrink:0; }
  .mail-ai { min-height:0; overflow-y:auto; }
}
</style>
