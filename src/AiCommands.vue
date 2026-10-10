<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { Sparkles, Send, RefreshCw, Check, Mail, Plus, X, Search } from 'lucide-vue-next'
const props = defineProps({ api: Function })
const prompt = ref(''), source = ref('both'), dictionaryId = ref(''), channel = ref('auto')
const options = ref(null), busy = ref(false), error = ref(''), notice = ref(''), plan = ref(null), chosen = ref([])
const tab = ref('all'), messages = ref([]), history = ref([])
const compose = ref(''), subject = ref(''), body = ref(''), contacts = ref([]), selected = ref([]), contactSearch = ref('')
const recipientFilter = ref(''), descriptionFilter = ref(''), fromDate = ref(''), toDate = ref(''), detail = ref(null)
const localDay = value => { const d = new Date(value); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}` }
const rows = computed(() => [
  ...history.value.flatMap(job => job.recipients.filter(person => person.status !== 'skipped').map(person => ({
    id: `${job.id}:${person.id}`, direction: 'history', recipient: person.name, address: person.channel === 'user' ? '' : person.address,
    sender: 'Ja', subject: job.subject, message: job.message, channel: person.channel, status: person.status,
    reason: person.reason, created_at: person.sent_at || job.sent_at || job.created_at,
  }))),
  ...messages.value.map(item => ({ ...item, direction: 'inbox', recipient: 'Ja', sender: item.sender_name, channel: 'user', status: item.read_at ? 'read' : 'unread' })),
].sort((a,b) => new Date(b.created_at) - new Date(a.created_at)))
const filteredRows = computed(() => rows.value.filter(item =>
  (tab.value === 'all' || item.direction === tab.value) &&
  `${item.recipient} ${item.address || ''} ${item.sender}`.toLocaleLowerCase('pl').includes(recipientFilter.value.trim().toLocaleLowerCase('pl')) &&
  `${item.subject} ${item.message}`.toLocaleLowerCase('pl').includes(descriptionFilter.value.trim().toLocaleLowerCase('pl')) &&
  (!fromDate.value || localDay(item.created_at) >= fromDate.value) && (!toDate.value || localDay(item.created_at) <= toDate.value)))
const filteredContacts = computed(() => contacts.value.filter(item =>
  (source.value === 'both' || (source.value === 'users' ? item.id.startsWith('u:') : item.id.startsWith('d:'))) &&
  (!dictionaryId.value || source.value === 'users' || item.id.startsWith('u:') || item.dictionary_id === dictionaryId.value) &&
  `${item.name} ${item.source}`.toLocaleLowerCase('pl').includes(contactSearch.value.trim().toLocaleLowerCase('pl'))))
const scopeContacts = computed(() => contacts.value.filter(item =>
  (source.value === 'both' || (source.value === 'users' ? item.id.startsWith('u:') : item.id.startsWith('d:'))) &&
  (!dictionaryId.value || source.value === 'users' || item.id.startsWith('u:') || item.dictionary_id === dictionaryId.value)))
async function openCompose(mode) {
  compose.value = mode; plan.value = null; chosen.value = []; selected.value = []; error.value = ''; source.value = 'both'; dictionaryId.value = ''; channel.value = 'auto'
  if (mode === 'manual') {
    contacts.value = []; contactSearch.value = ''
    busy.value = true
    try { contacts.value = await props.api('/messages/contacts') } catch (err) { error.value = err.message }
    finally { busy.value = false }
  }
}
async function prepareManual() {
  if (busy.value || !subject.value.trim() || !body.value.trim() || !selected.value.length) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api('/messages/prepare', 'POST', { subject: subject.value, message: body.value,
      recipients: selected.value.filter(id => scopeContacts.value.some(item => item.id === id)), source: source.value,
      dictionary_id: source.value !== 'users' && dictionaryId.value ? dictionaryId.value : null, channel: channel.value })
    plan.value = result; chosen.value = result.recipients.filter(item => item.available).map(item => item.id)
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
const unread = computed(() => messages.value.filter(item => !item.read_at).length)
const channelLabels = { user: 'W aplikacji', email: 'E-mail', sms: 'SMS' }
const statusLabels = { sent: 'Wysłano', failed: 'Błąd wysyłki', sending: 'Wysyłka niepotwierdzona', skipped: 'Pominięto', pending: 'Oczekuje' }
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
let timer, disposed = false, loading = false
async function load() {
  if (loading) return
  loading = true
  try {
    const [config, inbox, sent] = await Promise.all([props.api('/ai/commands/options'), props.api('/messages'), props.api('/ai/commands/history')])
    if (!disposed) { options.value = config; messages.value = inbox; history.value = sent }
  } catch (err) { if (!disposed) error.value = err.message }
  finally { loading = false }
}
async function prepare() {
  if (busy.value || !prompt.value.trim()) return
  if (!options.value?.ai.available) { error.value = options.value?.ai.message || 'AI wymaga konfiguracji OpenAI na serwerze.'; return }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await props.api('/ai/commands/plan', 'POST', { prompt: prompt.value, source: source.value,
      dictionary_id: source.value !== 'users' && dictionaryId.value ? dictionaryId.value : null, channel: channel.value })
    plan.value = result; chosen.value = result.action === 'message' ? result.recipients.filter(item => item.available).map(item => item.id) : []
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function execute() {
  if (busy.value || !plan.value?.id || !chosen.value.length) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api(`/ai/commands/${plan.value.id}/execute`, 'POST', { confirmed: true,
      subject: plan.value.subject, message: plan.value.message, recipients: chosen.value })
    const sent = result.recipients.filter(item => item.status === 'sent').length
    const failed = result.recipients.filter(item => item.status === 'failed').length
    notice.value = `Wysłano: ${sent}${failed ? ` · błędy: ${failed}` : ''}. Szczegóły są na liście wiadomości.`
    plan.value = null; chosen.value = []; compose.value = ''; tab.value = 'history'; await load()
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function markRead(item) {
  if (busy.value || item.read_at) return
  busy.value = true; error.value = ''
  try { const result = await props.api(`/messages/${item.id}/read`, 'POST'); item.read_at = result.read_at }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(() => { load(); timer = setInterval(() => { if (!busy.value) load() }, 15000) })
onBeforeUnmount(() => { disposed = true; clearInterval(timer) })
</script>

<template>
<section class="ai-commands">
  <header class="commands-heading"><div class="commands-title"><span class="ai-command-icon"><Mail :size="24" /></span><div><h1>Wiadomości</h1><p>Rozmowy, powiadomienia i historia wysyłek w jednym miejscu.</p></div></div>
    <div class="heading-actions"><button :disabled="busy" @click="openCompose('manual')"><Plus :size="16" /> Nowa wiadomość</button><button class="primary" :disabled="busy" @click="openCompose('ai')"><Sparkles :size="16" /> Nowa wiadomość AI</button><button class="icon-button" :disabled="busy" aria-label="Odśwież wiadomości" @click="load"><RefreshCw :size="17" /></button></div>
  </header>
  <p v-if="error && !compose" class="error" role="alert">{{ error }}</p><p v-if="notice" class="command-notice" role="status">{{ notice }}</p>
  <nav class="commands-tabs" aria-label="Rodzaj wiadomości"><button :aria-pressed="tab === 'all'" @click="tab = 'all'">Wszystkie</button><button :aria-pressed="tab === 'inbox'" @click="tab = 'inbox'">Odebrane <span v-if="unread">{{ unread }}</span></button><button :aria-pressed="tab === 'history'" @click="tab = 'history'">Wysłane</button></nav>
  <div class="message-filters"><label>Do kogo / od kogo<input v-model="recipientFilter" placeholder="Osoba lub adres" /></label><label>Opis<input v-model="descriptionFilter" placeholder="Szukaj w temacie i treści" /></label><label>Wysłano od<input v-model="fromDate" type="date" :max="toDate || undefined" /></label><label>Do<input v-model="toDate" type="date" :min="fromDate || undefined" /></label><button class="icon-button" aria-label="Wyczyść filtry" @click="recipientFilter = ''; descriptionFilter = ''; fromDate = ''; toDate = ''"><X :size="16" /></button></div>
  <div class="panel message-table"><table><thead><tr><th>Do kogo / od kogo</th><th>Temat i opis</th><th>Data wysłania</th><th>Status</th><th></th></tr></thead><tbody><tr v-for="item in filteredRows" :key="item.id" :class="{ 'unread-row': item.status === 'unread' }"><td><strong>{{ item.direction === 'inbox' ? item.sender : item.recipient }}</strong><small>{{ item.direction === 'inbox' ? 'Od: ' + item.sender : 'Do: ' + item.recipient }}<template v-if="item.address"> · {{ item.address }}</template></small><small>{{ channelLabels[item.channel] }}</small></td><td><button class="message-subject" @click="detail = item">{{ item.subject }}</button><p class="message-excerpt">{{ item.message }}</p></td><td class="message-date">{{ date(item.created_at) }}</td><td><span class="delivery-status" :class="item.status">{{ item.status === 'unread' ? 'Nowa' : item.status === 'read' ? 'Przeczytana' : statusLabels[item.status] }}</span><small v-if="item.status === 'failed'">{{ item.reason }}</small></td><td><button v-if="item.status === 'unread'" class="icon-button" title="Oznacz jako przeczytaną" aria-label="Oznacz jako przeczytaną" :disabled="busy" @click="markRead(messages.find(message => message.id === item.id))"><Check :size="16" /></button></td></tr></tbody></table><p v-if="!filteredRows.length" class="commands-empty">Brak wiadomości spełniających wybrane filtry.</p></div>
  <div v-if="compose" class="modal-backdrop" @click.self="!busy && (compose = '')" @keydown.esc="!busy && (compose = '')"><section class="panel compose-dialog" role="dialog" aria-modal="true" aria-labelledby="compose-title"><header class="compose-heading"><div><h2 id="compose-title">{{ compose === 'ai' ? 'Nowa wiadomość AI' : 'Nowa wiadomość' }}</h2><p>Przygotuj treść i sprawdź odbiorców przed wysłaniem.</p></div><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="compose = ''"><X :size="20" /></button></header><div class="compose-content"><p v-if="error" class="error" role="alert">{{ error }}</p>
    <form v-if="compose === 'manual' && !plan" class="command-form" @submit.prevent="prepareManual"><label>Temat<input v-model="subject" required maxlength="200" :disabled="busy" placeholder="Temat wiadomości" /></label><label>Wiadomość<textarea v-model="body" required maxlength="5000" rows="5" :disabled="busy" placeholder="Napisz wiadomość..." /></label><div class="command-options"><label>Odbiorcy<select v-model="source" :disabled="busy"><option value="both">Użytkownicy i słowniki</option><option value="users">Użytkownicy aplikacji</option><option value="dictionaries">Słowniki</option></select></label><label v-if="source !== 'users'">Słownik<select v-model="dictionaryId" :disabled="busy"><option value="">Wszystkie</option><option v-for="item in options?.dictionaries || []" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>Kanał<select v-model="channel" :disabled="busy"><option value="auto">Automatycznie</option><option value="user">W aplikacji</option><option value="email">E-mail</option><option value="sms">SMS</option></select></label></div><label>Szukaj odbiorcy<input v-model="contactSearch" placeholder="Imię, nazwisko lub słownik" /></label><div class="command-recipients"><label v-for="item in filteredContacts" :key="item.id" class="command-person"><input v-model="selected" type="checkbox" :value="item.id" :disabled="busy" /><span><strong>{{ item.name }}</strong><small>{{ item.source }} · {{ Object.keys(item.channels).map(key => channelLabels[key]).join(', ') || 'Brak danych kontaktowych' }}</small></span></label><p v-if="!filteredContacts.length" class="commands-empty">Nie znaleziono odbiorców.</p></div><footer><span>{{ selected.filter(id => scopeContacts.some(item => item.id === id)).length }} wybranych</span><button class="primary" type="submit" :disabled="busy || !selected.some(id => scopeContacts.some(item => item.id === id))">Podgląd wiadomości <Send :size="16" /></button></footer></form>
      <form v-if="compose === 'ai'" class="panel command-form" @submit.prevent="prepare"><label>Co ma zrobić system?<textarea v-model="prompt" required maxlength="6000" rows="4" :disabled="busy" placeholder="Wyślij do pracowników wiadomość: Spotkanie na sali o godzinie 19:00." /></label><div class="command-options"><label>Gdzie szukać odbiorców<select v-model="source" :disabled="busy"><option value="both">Użytkownicy i słowniki</option><option value="users">Użytkownicy aplikacji</option><option value="dictionaries">Słowniki</option></select></label><label v-if="source !== 'users'">Słownik<select v-model="dictionaryId" :disabled="busy"><option value="">Wszystkie słowniki</option><option v-for="item in options?.dictionaries || []" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>Kanał<select v-model="channel" :disabled="busy"><option value="auto">Z polecenia lub automatycznie</option><option value="user">W aplikacji</option><option value="email">E-mail</option><option value="sms">SMS</option></select></label></div><footer><p>AI dobierze osoby i przygotuje wiadomość. Sprawdź podgląd przed wysłaniem.</p><button class="primary" :disabled="busy || !prompt.trim() || !options?.ai.available" type="submit"><Sparkles :size="17" /> {{ busy ? 'Przygotowywanie…' : 'Przygotuj polecenie' }}</button></footer><p v-if="options && !options.ai.available" class="error">{{ options.ai.message }}</p></form>
      <article v-if="plan" class="panel command-preview"><button v-if="compose === 'manual'" :disabled="busy" @click="plan = null; chosen = []">Edytuj odbiorców i treść</button><header><h2>{{ plan.action === 'clarify' ? 'Doprecyzuj polecenie' : 'Podgląd wiadomości' }}</h2><p>{{ plan.explanation }}</p></header><template v-if="plan.action === 'message'"><label>Temat<input v-model="plan.subject" maxlength="200" :disabled="busy" /></label><label>Wiadomość<textarea v-model="plan.message" rows="4" maxlength="5000" :disabled="busy" /></label><h3>Odbiorcy <span>{{ chosen.length }}/{{ plan.recipients.length }}</span></h3><div class="command-recipients"><label v-for="item in plan.recipients" :key="item.id" class="command-person"><input v-model="chosen" type="checkbox" :value="item.id" :disabled="busy || !item.available" /><span><strong>{{ item.name }}</strong><small>{{ item.source }} · {{ channelLabels[item.channel] || 'Brak kanału' }}<template v-if="item.channel !== 'user' && item.address"> · {{ item.address }}</template></small><small v-if="item.reason" class="recipient-warning">{{ item.reason }}</small></span></label></div><footer><span>{{ chosen.length }} wybranych osób</span><button class="primary" :disabled="busy || !chosen.length || !plan.subject.trim() || !plan.message.trim()" @click="execute"><Send :size="16" /> {{ busy ? 'Wysyłanie…' : 'Wyślij wiadomość' }}</button></footer></template></article>

</div></section></div>
<div v-if="detail" class="modal-backdrop" @click.self="detail = null" @keydown.esc="detail = null"><section class="panel compose-dialog" role="dialog" aria-modal="true" aria-labelledby="message-detail-title"><header class="compose-heading"><div><h2 id="message-detail-title">{{ detail.subject }}</h2><p>{{ detail.direction === 'inbox' ? 'Od: ' + detail.sender : 'Do: ' + detail.recipient }} · {{ date(detail.created_at) }}</p></div><button class="icon-button" aria-label="Zamknij" @click="detail = null"><X :size="20" /></button></header><div class="compose-content message-body">{{ detail.message }}</div></section></div>
</section>
</template>

<style scoped>
.heading-actions { display:flex; gap:8px; flex-wrap:wrap; }.heading-actions button { font-size:12px; }
.message-filters { display:grid; grid-template-columns: 1.2fr 1.5fr 1fr 1fr auto; gap:12px; align-items:end; margin-bottom:20px; }.message-filters label { font-size:11px; color:var(--muted); margin:0; }.message-filters input { margin-top:7px; min-width:0; }
.message-table { border-radius:16px; overflow-x:auto; }.message-table table { width:100%; border-collapse:collapse; text-align:left; }.message-table th { font-size:11px; color:var(--muted); font-weight:500; background:var(--surface-soft); padding:16px; }.message-table td { padding:18px 16px; border-top:1px solid var(--border); font-size:12px; vertical-align:top; }.message-table td:first-child { min-width:160px; }.message-table strong { font-weight:500; }.message-table small { display:block; font-size:11px; color:var(--muted); margin-top:6px; overflow-wrap:anywhere; }.message-subject { border:0; padding:0; background:transparent; font-size:13px; text-align:left; color:var(--text); }.message-excerpt { color:var(--muted); font-size:12px; line-height:1.6; margin:7px 0 0; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; white-space:pre-wrap; overflow-wrap:anywhere; max-width:480px; }.message-date { white-space:nowrap; color:var(--muted); }.unread-row { background:var(--surface-soft); }.delivery-status { display:inline-block; white-space:nowrap; padding:5px 8px; border-radius:6px; background:var(--surface-soft); }.delivery-status.sent, .delivery-status.read { color:var(--success); background:var(--success-soft); }.delivery-status.unread { color:var(--accent); background:var(--accent-soft); }
.compose-dialog { width:min(820px,100%); max-height:90vh; display:flex; flex-direction:column; border-radius:20px; overflow:hidden; }.compose-heading { padding:22px 26px; display:flex; justify-content:space-between; gap:16px; border-bottom:1px solid var(--border); }.compose-heading h2 { margin:0; font-size:19px; }.compose-heading p { font-size:12px; color:var(--muted); margin:8px 0 0; }.compose-content { padding:24px; overflow-y:auto; }.compose-content .command-form { padding:0; border:0; }.compose-content .command-form label { margin-bottom:16px; }.compose-content .command-person { margin:0 !important; }.compose-content .command-form footer { margin-top:20px; color:var(--muted); font-size:12px; }.message-body { white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.8; font-size:14px; }
@media(max-width:900px) { .commands-heading { flex-wrap:wrap; }.message-filters { grid-template-columns:1fr 1fr; }.compose-content { padding:16px; }.compose-heading { padding:20px; } }
.commands-heading, .commands-title, .commands-tabs { display: flex; align-items: center; gap: 12px; }.commands-heading { justify-content: space-between; margin: 24px 0; }.ai-command-icon { display: grid; place-items: center; width: 54px; height: 54px; background: var(--accent-soft); color: var(--accent); border-radius: 15px; }h1 { margin: 0; font-size: 26px; }.commands-title p { color: var(--muted); font-size: 12px; margin: 7px 0 0; }.commands-tabs { flex-wrap: wrap; gap: 8px; margin-bottom: 22px; }.commands-tabs button { border: none; background: transparent; color: var(--muted); font-size: 12px; }.commands-tabs button[aria-pressed='true'] { color: var(--accent); background: var(--accent-soft); }.commands-tabs span { font-size: 10px; padding: 2px 5px; border-radius: 4px; background: var(--surface); }
.command-form, .command-preview { padding: 24px; border-radius: 16px; margin-bottom: 20px; }.command-options { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }.command-form label, .command-preview label { color: var(--secondary); font-size: 12px; }.command-form textarea { font-size: 14px; line-height: 1.7; }.command-form footer, .command-preview footer { display: flex; align-items: center; justify-content: space-between; gap: 15px; flex-wrap: wrap; }.command-form footer p { color: var(--muted); font-size: 11px; flex: 1; line-height: 1.7; }.command-form footer button { font-size: 12px; }.command-preview { display: flex; flex-direction: column; gap: 16px; }.command-preview header h2, .message-card h2 { font-size: 17px; margin: 0; }.command-preview header p { color: var(--muted); font-size: 12px; line-height: 1.6; margin: 8px 0 0; }.command-preview h3 { font-size: 13px; margin: 0; }.command-preview h3 span { color: var(--muted); font-size: 11px; font-weight: 400; margin-left: 5px; }.command-recipients { border: 1px solid var(--border); border-radius: 12px; max-height: 300px; overflow-y: auto; }.command-person { display: flex; flex-direction: row; align-items: flex-start; gap: 12px; padding: 14px; border-bottom: 1px solid var(--border); margin: 0; }.command-person:last-child { border: none; }.command-person input { width: 15px; height: 15px; margin-top: 2px; accent-color: var(--accent); }.command-person strong { font-size: 13px; font-weight: 500; }.command-person small { display: block; font-size: 11px; color: var(--muted); margin-top: 5px; overflow-wrap: anywhere; }.command-person .recipient-warning { color: var(--danger); }.command-preview footer { border-top: 1px solid var(--border); padding-top: 16px; font-size: 12px; color: var(--muted); }.command-notice { font-size: 12px; color: var(--success); }
.command-cards { display: grid; gap: 16px; }.message-card { padding: 22px; border-radius: 14px; }.message-card.unread { border-color: var(--focus-ring); }.message-card header { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }.message-card small { color: var(--muted); font-size: 11px; }.message-card > small { display: block; margin-top: 8px; }.message-card p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; font-size: 13px; color: var(--secondary); }.message-card button { font-size: 11px; }.message-new { color: var(--accent); background: var(--accent-soft); border-radius: 6px; padding: 4px 7px; font-size: 10px; }.message-card ul { list-style: none; padding: 0; margin: 16px 0 0; }.message-card li { padding: 10px 0; border-top: 1px solid var(--border); display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; font-size: 12px; }.delivery-status { color: var(--muted); font-size: 11px; text-align: right; }.delivery-status.sent { color: var(--success); }.delivery-status.failed { color: var(--danger); }.delivery-status small { display: block; max-width: 300px; margin-top: 4px; }.commands-empty { text-align: center; padding: 40px; color: var(--muted); font-size: 13px; }
</style>
