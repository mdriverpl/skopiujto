<script setup>
import { computed, onMounted, ref } from 'vue'
import { Send, X, Mail, MessageSquare, Users, History, BookOpen, Search, UserRound, Check } from 'lucide-vue-next'
import ComposeAttachments from './ComposeAttachments.vue'
import { attachmentSelection, hasAttachmentChanges, saveAttachmentSelection, downloadMailArchive } from './composeAttachments.js'
const props = defineProps({ api: Function, channel: String, group: { type: Boolean, default: true }, reply: Boolean, initialSubject: String, initialContent: String, initialRecipient: String, initialRecipientId: String, embedded: Boolean, attachmentsTarget: String })
const emit = defineEmits(['close', 'switch-channel', 'manual-email', 'sent'])
const subject = ref(props.initialSubject || ''), content = ref(props.initialContent || '')
const contacts = ref([]), selected = ref([]), search = ref(''), config = ref(null)
const dictionaryId = ref('')
const composeFiles = ref(attachmentSelection()), attachmentDraft = ref(null)
const recipientSource = ref('contacts'), directEmail = ref(props.initialRecipient || '')
const isGroup = computed(() => props.group !== false)
const activeSource = computed(() => (!isGroup.value ? selected.value[0]?.startsWith('h:') : recipientSource.value === 'history') ? 'history' : props.channel === 'user' ? 'users' : 'dictionaries')
const manualAddress = computed(() => ['email', 'sms'].includes(props.channel) && !selected.value.length ? directEmail.value.trim() : '')
const recipientCount = computed(() => selected.value.length + (manualAddress.value ? 1 : 0))
let contactsRequest = 0
const loading = ref(true), busy = ref(false), error = ref(''), plan = ref(null), result = ref(null)
const limit = computed(() => props.channel === 'sms' ? 1200 : 5000)
const available = computed(() => !!config.value?.channels?.[props.channel]?.configured)
const recipients = computed(() => contacts.value.filter(person => !!person.channels[props.channel]))
const chosenRecipients = computed(() => recipients.value.filter(person => selected.value.includes(person.id)))
function initials(name) { return name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toLocaleUpperCase('pl') }
function removeRecipient(id) { selected.value = selected.value.filter(value => value !== id); plan.value = null }
const filtered = computed(() => recipients.value.filter(person => `${person.name} ${person.source} ${person.channels[props.channel]}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
const allSelected = computed(() => filtered.value.length > 0 && filtered.value.every(person => selected.value.includes(person.id)))
const someSelected = computed(() => !allSelected.value && filtered.value.some(person => selected.value.includes(person.id)))
const recipientLabel = computed(() => {
  const names = recipients.value.filter(person => selected.value.includes(person.id)).map(person => person.name)
  return names.length ? names.slice(0, 2).join(', ') + (names.length > 2 ? ` +${names.length - 2}` : '') : 'Wybierz odbiorców z listy'
})
function toggleAll() {
  const ids = new Set(filtered.value.map(person => person.id))
  selected.value = allSelected.value ? selected.value.filter(id => !ids.has(id)) : [...new Set([...selected.value, ...ids])]
  plan.value = null
}
const canSend = computed(() => !busy.value && !loading.value && !result.value && available.value && subject.value.trim()
  && content.value.trim() && content.value.length <= limit.value && recipientCount.value > 0)
function pickRecipient() {
  const person = recipients.value.find(person => (props.channel === 'user' ? person.name : person.channels[props.channel]) === directEmail.value)
  selected.value = person ? [person.id] : []
  plan.value = null
}
function switchChannel(channel) {
  if (!busy.value && !props.reply && channel !== props.channel) emit('switch-channel', { channel, subject: subject.value, content: content.value, recipient: '' })
}
async function chooseSource(source) { recipientSource.value = source; await loadContacts() }
function close() { if (!busy.value) emit('close') }
async function load() {
  loading.value = true; error.value = ''
  try { config.value = await props.api('/ai/commands/options'); await loadContacts() }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}
async function loadContacts() {
  const request = ++contactsRequest
  loading.value = true; error.value = ''; selected.value = []; contacts.value = []; plan.value = null
  const params = new URLSearchParams({ source: activeSource.value })
  if (activeSource.value === 'dictionaries' && dictionaryId.value) params.set('dictionary_id', dictionaryId.value)
  try {
    const rows = await props.api(`/messages/contacts?${params}`)
    const history = !isGroup.value ? await props.api('/messages/contacts?source=history') : []
    if (request === contactsRequest) {
      contacts.value = [...rows, ...history.filter(person => !rows.some(existing => existing.id === person.id))]
      if (!isGroup.value) {
        const person = contacts.value.find(person => person.id === props.initialRecipientId)
        if (person) { selected.value = [person.id]; directEmail.value = props.channel === 'user' ? person.name : person.channels[props.channel] }
        else pickRecipient()
      }
    }
  } catch (err) { if (request === contactsRequest) error.value = err.message }
  finally { if (request === contactsRequest) loading.value = false }
}
async function saveFiles() {
  const selection = composeFiles.value
  if (!hasAttachmentChanges(selection)) return null
  const saved = attachmentDraft.value
  if (saved && !selection.files.length && !selection.drive.length && !selection.removed.length &&
      selection.zip_enabled === !!saved.zip_enabled && selection.zip_name === saved.zip_name && selection.zip_password === (saved.zip_password || '')) return saved
  if (!saved) attachmentDraft.value = await props.api('/client-mail/drafts', 'POST', { subject: subject.value, content: content.value })
  attachmentDraft.value = await saveAttachmentSelection(props.api, attachmentDraft.value, selection)
  composeFiles.value = attachmentSelection(attachmentDraft.value)
  plan.value = null
  return attachmentDraft.value.attachments.length ? attachmentDraft.value : null
}
async function downloadZip() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { const draft = await saveFiles(); if (draft) await downloadMailArchive(draft.id) }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function send() {
  if (!canSend.value) return
  busy.value = true; error.value = ''
  try {
    const attachment = props.channel === 'email' ? await saveFiles() : null
    const results = []
    const manual = manualAddress.value
    const batches = []
    let offset = 0
    do {
      const size = offset === 0 && manual ? 99 : 100
      batches.push(selected.value.slice(offset, offset + size)); offset += size
    } while (offset < selected.value.length)
    for (let index = 0; index < batches.length; index++) {
      if (!plan.value) {
        plan.value = await props.api('/messages/prepare', 'POST', { subject: subject.value.trim(), message: content.value.trim(),
          recipients: batches[index], source: activeSource.value, direct_email: props.channel === 'email' && index === 0 && manual ? manual : null,
          direct_sms: props.channel === 'sms' && index === 0 && manual ? manual : null,
          dictionary_id: activeSource.value === 'dictionaries' && dictionaryId.value ? dictionaryId.value : null, channel: props.channel,
          ...(attachment ? { attachment_mail_id: attachment.id, attachment_version: attachment.version } : {}) })
        const unavailable = plan.value.recipients.filter(person => !person.available)
        if (unavailable.length || !plan.value.recipients.length) {
          const reason = unavailable.map(person => `${person.name}: ${person.reason}`).join('; ')
          plan.value = null
          throw new Error(reason || 'Wybierz dostępnych odbiorców.')
        }
      }
      const batch = await props.api(`/ai/commands/${plan.value.id}/execute`, 'POST', { confirmed: true,
        subject: plan.value.subject, message: plan.value.message, recipients: plan.value.recipients.map(person => person.id) })
      results.push(...batch.recipients)
      result.value = { recipients: [...results] }
      plan.value = null
    }
    const sent = result.value.recipients.filter(person => person.status === 'sent').length
    if (sent === result.value.recipients.length && sent > 0) {
      emit('sent', `${props.channel === 'sms' ? 'SMS' : props.channel === 'email' ? 'E-mail' : 'Portal'} — wysłano wiadomość do ${sent} odbiorców.`)
    } else error.value = 'Nie wszystkie wiadomości zostały wysłane. Sprawdź wynik poniżej.'
  } catch (err) { error.value = result.value ? `Wysyłka przerwana. Obsłużono ${result.value.recipients.length} z ${recipientCount.value} odbiorców. ${err.message}` : err.message }
  finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <div class="channel-message-overlay" :class="{ embedded }" @keydown.esc.stop.prevent="close" @click.self="!embedded && close()"><form class="channel-message-dialog" :class="{ 'group-compose': isGroup }" :role="embedded ? undefined : 'dialog'" :aria-modal="embedded ? undefined : 'true'" aria-labelledby="channel-message-title" novalidate @submit.prevent="send">
    <header><div class="compose-heading"><span class="compose-emblem"><Send :size="23" /></span><div><h2 id="channel-message-title">{{ reply ? 'Odpowiedź' : isGroup ? 'Wiadomość do wielu osób' : 'Nowa wiadomość' }}</h2><p>{{ isGroup ? 'Wybierz odbiorców i napisz do nich w jednym miejscu.' : 'Wszystko, czego potrzebujesz, by być w kontakcie.' }}</p></div></div><button type="button" class="compose-close" :disabled="busy" aria-label="Zamknij wiadomość" @click="close"><X :size="19" /></button></header>
    <p v-if="error" class="channel-error" role="alert">{{ error }}</p><p v-if="loading" role="status">Wczytywanie odbiorców…</p>
    <p v-if="config && !available" class="channel-error">{{ config.channels[channel]?.message || 'Ten kanał wymaga konfiguracji.' }}</p>
    <fieldset :class="{ 'compose-columns': isGroup }" :disabled="busy || loading || !!result" @input="plan = null" @change="plan = null">
      <aside v-if="isGroup" class="channel-to" aria-label="Lista odbiorców">
        <div class="recipient-heading"><h3><Users :size="17" />Odbiorcy</h3><span>{{ filtered.length }}</span></div>
        <div class="recipient-source-tabs" role="group" aria-label="Źródło odbiorców"><button type="button" :aria-pressed="recipientSource === 'history'" @click="chooseSource('history')"><History :size="15" />Historia</button><button type="button" :aria-pressed="recipientSource === 'contacts'" @click="chooseSource('contacts')"><BookOpen :size="15" />{{ channel === 'user' ? 'Pracownicy' : 'Słowniki' }}</button></div>
        <div class="channel-picker-filters"><label v-if="activeSource === 'dictionaries'">Słownik<select v-model="dictionaryId" @change="loadContacts"><option value="">Wszystkie słowniki</option><option v-for="dictionary in config?.dictionaries || []" :key="dictionary.id" :value="dictionary.id">{{ dictionary.name }}</option></select></label>
        <label class="recipient-search"><span class="sr-only">Szukaj odbiorcy</span><Search :size="16" /><input v-model="search" type="search" placeholder="Znajdź osobę lub kontakt…" /></label></div>
        <label class="channel-select-all"><input type="checkbox" :checked="allSelected" :indeterminate="someSelected" :disabled="!filtered.length" @change="toggleAll" /><span>Zaznacz wszystkich <small>({{ filtered.length }})</small></span></label>
        <div class="channel-recipients"><label v-for="(person, index) in filtered" :key="person.id"><input v-model="selected" type="checkbox" :value="person.id" /><span class="contact-avatar" :class="`avatar-${index % 3}`" aria-hidden="true">{{ initials(person.name) }}</span><span class="contact-details"><strong>{{ person.name }}</strong><small>{{ channel === 'sms' ? person.channels.sms : channel === 'email' ? person.channels.email : person.source }}</small></span></label><div v-if="!loading && !filtered.length" class="recipients-empty"><span><Users :size="25" /></span><strong>Nie znaleziono kontaktów</strong><p>{{ search ? 'Spróbuj zmienić wyszukiwanie.' : channel === 'user' ? 'Wybierz inną listę odbiorców.' : 'Wybierz inny słownik lub uzupełnij dane kontaktowe.' }}</p></div></div>
        <div class="selection-note"><Check :size="14" /><span>Wybrano <strong>{{ selected.length }}</strong> {{ selected.length === 1 ? 'osobę' : 'osób' }}</span></div>
      </aside>
      <section class="channel-message-panel">
        <div v-if="isGroup" class="compose-field"><span class="field-label">Do:</span><div class="recipient-summary" :class="{ 'has-recipients': chosenRecipients.length }"><template v-if="chosenRecipients.length"><span v-for="person in chosenRecipients.slice(0, 8)" :key="person.id" class="recipient-chip"><span>{{ person.name }}</span><button type="button" :aria-label="`Usuń odbiorcę: ${person.name}`" @click="removeRecipient(person.id)"><X :size="12" /></button></span><span v-if="chosenRecipients.length > 8" class="recipient-more">+{{ chosenRecipients.length - 8 }}</span></template><span v-else class="recipient-placeholder"><UserRound :size="17" />Wybierz osoby z listy odbiorców</span></div></div>
        <label v-else>Do:<input v-model="directEmail" list="channel-recipient-suggestions" :type="channel === 'sms' ? 'tel' : 'text'" autocomplete="off" :placeholder="channel === 'user' ? 'Wybierz osobę z listy' : channel === 'sms' ? 'Numer telefonu lub kontakt' : 'Adres e-mail lub kontakt'" required @input="pickRecipient" /><datalist id="channel-recipient-suggestions"><option v-for="person in recipients" :key="person.id" :value="channel === 'user' ? person.name : person.channels[channel]">{{ person.name }} · {{ person.source }}</option></datalist></label>
        <div class="compose-source compose-field"><span class="field-label">Źródło:</span><div class="channel-options" role="group" aria-label="Źródło wiadomości"><button v-for="option in [{ value: 'email', label: 'Email', icon: Mail }, { value: 'sms', label: 'SMS', icon: MessageSquare }, { value: 'user', label: 'Portal', icon: Users }]" :key="option.value" type="button" :aria-pressed="channel === option.value" :disabled="reply" @click="switchChannel(option.value)"><component :is="option.icon" :size="16" />{{ option.label }}<Check v-if="channel === option.value" class="channel-check" :size="13" /></button></div><small v-if="reply">Ustawione zgodnie z wiadomością, na którą odpowiadasz.</small></div>
        <label>Temat:<input v-model="subject" required maxlength="200" placeholder="Temat wiadomości" /></label>
        <label class="message-body-field">Treść:<textarea v-model="content" required :maxlength="limit" rows="10" placeholder="Napisz swoją wiadomość…" /><small class="channel-length">{{ content.length.toLocaleString('pl') }} / {{ limit.toLocaleString('pl') }}</small></label>
        <p v-if="channel === 'user'" class="channel-hint">Wiadomość zostanie dostarczona w portalu, bez e-maila.</p>
        <Teleport :to="attachmentsTarget || 'body'" :disabled="!attachmentsTarget" defer><ComposeAttachments v-if="channel === 'email'" v-model="composeFiles" :api="api" :disabled="busy || loading || !!result" @update:model-value="plan = null" @download-zip="downloadZip" /></Teleport>
      </section>
    </fieldset>
    <ul v-if="result" class="channel-results"><li v-for="person in result.recipients" :key="person.id"><strong>{{ person.name }}</strong> — {{ person.status === 'sent' ? 'Wysłano' : person.reason || 'Wysyłka niepotwierdzona' }}</li></ul>
    <footer><span class="send-summary"><Users :size="16" /><span><strong>{{ recipientCount }}</strong> {{ recipientCount === 1 ? 'odbiorca' : 'odbiorców' }}<small>{{ channel === 'email' ? 'Wiadomość e-mail' : channel === 'sms' ? 'Wiadomość SMS' : 'Wiadomość w portalu' }}</small></span></span><button type="button" class="compose-cancel" :disabled="busy" @click="close">{{ result ? 'Zamknij' : 'Anuluj' }}</button><button v-if="!result" type="submit" class="primary" :disabled="!canSend"><Send :size="16" />{{ busy ? 'Wysyłanie…' : 'Wyślij wiadomość' }}</button></footer>
  </form></div>
</template>
<style scoped>
.channel-message-overlay { position:fixed; inset:0; z-index:100; display:grid; place-items:center; padding:24px; background:#17223952; backdrop-filter:blur(5px); }
.channel-message-dialog { box-sizing:border-box; display:flex; flex-direction:column; width:min(660px,100%); max-height:92dvh; overflow:auto; margin:0; padding:0; color:var(--text); background:var(--surface); border:1px solid var(--border); border-radius:22px; box-shadow:0 24px 90px #14213b30; }
.channel-message-dialog.group-compose { width:min(1060px,100%); }
header { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:25px 28px; border-bottom:1px solid var(--border); background:linear-gradient(110deg,color-mix(in srgb,var(--accent) 4%,var(--surface)),var(--surface) 70%); }
.compose-heading { display:flex; align-items:center; gap:14px; min-width:0; }.compose-emblem { display:grid; place-items:center; width:46px; height:46px; flex-shrink:0; color:var(--accent); background:var(--accent-soft); border-radius:14px; }.compose-heading h2 { margin:0; font-size:18px; font-weight:600; letter-spacing:-.4px; line-height:1.4; }.compose-heading p { margin:5px 0 0; color:var(--muted); font-size:12px; line-height:1.5; }.compose-close { display:grid; place-items:center; padding:8px; border:0; border-radius:9px; background:transparent; color:var(--muted); }.compose-close:hover { background:var(--surface-soft); color:var(--text); }
fieldset { display:grid; gap:18px; padding:26px 28px; margin:0; border:0; min-width:0; }.compose-columns { grid-template-columns:minmax(245px,.85fr) minmax(0,1.65fr); gap:26px; }.channel-to { display:flex; flex-direction:column; min-width:0; padding:18px; background:color-mix(in srgb,var(--accent) 2%,var(--surface-soft)); border:1px solid var(--border); border-radius:15px; }
.recipient-heading { display:flex; align-items:center; justify-content:space-between; margin-bottom:18px; }.recipient-heading h3 { display:flex; align-items:center; gap:8px; margin:0; font-size:13px; font-weight:600; }.recipient-heading h3 svg { color:var(--accent); }.recipient-heading > span { min-width:23px; box-sizing:border-box; padding:3px 7px; border:1px solid var(--border); border-radius:7px; color:var(--muted); background:var(--surface); font-size:11px; text-align:center; }
.recipient-source-tabs { display:flex; gap:3px; padding:3px; margin-bottom:18px; border:1px solid var(--border); border-radius:10px; background:var(--surface); }.recipient-source-tabs button { display:flex; align-items:center; justify-content:center; flex:1; gap:6px; padding:9px 5px; border:1px solid transparent; border-radius:7px; background:transparent; color:var(--muted); font-size:11px; }.recipient-source-tabs button[aria-pressed="true"] { color:var(--accent); background:var(--accent-soft); }
.channel-picker-filters { display:grid; gap:14px; margin-bottom:16px; }.channel-picker-filters label,.channel-message-panel > label,.compose-field { display:grid; gap:8px; min-width:0; font-size:12px; font-weight:500; color:var(--secondary); }.channel-message-panel { display:flex; flex-direction:column; gap:19px; min-width:0; padding:2px 0; }.field-label { font-size:12px; font-weight:500; color:var(--secondary); }
input:not([type="checkbox"]),textarea,select { width:100%; box-sizing:border-box; min-width:0; padding:11px 13px; border:1px solid var(--border); border-radius:10px; background:var(--surface); color:var(--text); font:inherit; font-size:12px; font-weight:400; box-shadow:none; outline:none; transition:border-color .15s,box-shadow .15s; }input:focus,textarea:focus,select:focus { border-color:color-mix(in srgb,var(--accent) 55%,var(--border)); box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 8%,transparent); }input::placeholder,textarea::placeholder { color:var(--muted); font-weight:400; }
.recipient-search { position:relative; }.recipient-search > svg { position:absolute; left:11px; top:50%; transform:translateY(-50%); color:var(--muted); pointer-events:none; }.recipient-search input { padding-left:34px; font-size:11px; }.sr-only { position:absolute; width:1px; height:1px; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
.channel-select-all { display:flex; align-items:center; gap:9px; padding:0 2px 13px; border-bottom:1px solid var(--border); color:var(--secondary); font-size:11px; }.channel-select-all small { color:var(--muted); }.channel-select-all input,.channel-recipients input[type="checkbox"] { width:15px; height:15px; margin:0; flex-shrink:0; accent-color:var(--accent); }
.channel-recipients { flex:1; max-height:290px; min-height:180px; overflow:auto; padding:9px 0; scrollbar-width:thin; }.channel-recipients > label { display:flex; align-items:center; gap:9px; padding:10px 7px; margin-bottom:3px; border:1px solid transparent; border-radius:10px; cursor:pointer; }.channel-recipients > label:hover { background:var(--surface); }.channel-recipients > label:has(input:checked) { background:var(--surface); border-color:color-mix(in srgb,var(--accent) 20%,var(--border)); box-shadow:0 2px 5px #14213b04; }.contact-avatar { display:grid; place-items:center; flex-shrink:0; width:32px; height:32px; border-radius:11px; color:#7560b8; background:#eae4f7; font-size:10px; font-weight:600; }.contact-avatar.avatar-1 { color:#427f8b; background:#e0f0f2; }.contact-avatar.avatar-2 { color:#ac7a41; background:#f7ebd9; }.contact-details { min-width:0; flex:1; }.contact-details strong,.contact-details small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.contact-details strong { font-size:11px; font-weight:500; }.contact-details small { margin-top:4px; font-size:10px; color:var(--muted); font-weight:400; }
.recipients-empty { display:flex; flex-direction:column; align-items:center; padding:34px 8px; text-align:center; color:var(--muted); }.recipients-empty > span { display:grid; place-items:center; width:56px; height:56px; margin-bottom:14px; border:1px dashed color-mix(in srgb,var(--accent) 25%,var(--border)); border-radius:18px; background:var(--surface); color:color-mix(in srgb,var(--accent) 65%,var(--muted)); }.recipients-empty strong { font-size:12px; font-weight:500; color:var(--secondary); }.recipients-empty p { max-width:210px; margin:7px 0 0; font-size:11px; line-height:1.7; }
.selection-note { display:flex; align-items:center; gap:7px; padding-top:12px; border-top:1px solid var(--border); color:var(--muted); font-size:10px; }.selection-note svg,.selection-note strong { color:var(--accent); }
.recipient-summary { display:flex; align-items:center; flex-wrap:wrap; gap:6px; min-height:46px; box-sizing:border-box; padding:9px 11px; border:1px dashed color-mix(in srgb,var(--accent) 22%,var(--border)); border-radius:10px; background:color-mix(in srgb,var(--accent) 2%,var(--surface)); }.recipient-summary.has-recipients { border-style:solid; border-color:var(--border); background:var(--surface); }.recipient-placeholder { display:flex; align-items:center; gap:9px; font-size:11px; color:var(--muted); }.recipient-placeholder svg { color:var(--accent); }.recipient-chip { display:inline-flex; align-items:center; gap:5px; max-width:100%; padding:4px 7px 4px 9px; border-radius:7px; background:var(--accent-soft); color:var(--accent); font-size:11px; }.recipient-chip > span { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }.recipient-chip button { display:grid; place-items:center; padding:2px; border:0; border-radius:4px; background:transparent; color:inherit; }.recipient-chip button:hover { background:color-mix(in srgb,var(--accent) 12%,transparent); }.recipient-more { padding:4px; color:var(--muted); font-size:11px; }
.channel-options { display:flex; flex-wrap:wrap; gap:8px; }.channel-options button { display:inline-flex; align-items:center; justify-content:center; gap:8px; min-width:94px; padding:10px 13px; border:1px solid var(--border); border-radius:10px; background:var(--surface); color:var(--muted); font-size:12px; transition:background .15s,border-color .15s; }.channel-options button[aria-pressed="true"] { border-color:color-mix(in srgb,var(--accent) 28%,var(--border)); background:var(--accent-soft); color:var(--accent); }.channel-check { margin-left:3px; }.compose-source > small { font-size:10px; font-weight:400; color:var(--muted); }
.message-body-field { flex:1; position:relative; }.message-body-field textarea { min-height:205px; resize:vertical; line-height:1.8; padding:14px 15px 28px; }.channel-length { position:absolute; right:12px; bottom:10px; padding-left:6px; color:var(--muted); background:var(--surface); font-size:10px; font-weight:400; pointer-events:none; }.channel-hint { margin:0; color:var(--muted); font-size:11px; line-height:1.6; }.channel-error { margin:12px 28px 0; padding:10px 12px; border-radius:9px; background:color-mix(in srgb,#d94a65 7%,var(--surface)); color:var(--theme-danger,#ba253b); font-size:12px; line-height:1.6; }header ~ p[role="status"] { margin:12px 28px 0; font-size:12px; color:var(--muted); }
footer { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:18px 28px; border-top:1px solid var(--border); background:color-mix(in srgb,var(--surface-soft) 55%,var(--surface)); }footer .send-summary { display:flex; align-items:center; gap:9px; margin-right:auto; color:var(--secondary); font-size:11px; }.send-summary > svg { color:var(--accent); }.send-summary strong { font-weight:600; }.send-summary small { display:block; margin-top:3px; color:var(--muted); font-size:10px; }footer button { display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:11px 16px; border-radius:10px; font-size:12px; }.compose-cancel { background:var(--surface); border:1px solid var(--border); color:var(--secondary); }footer .primary { padding-inline:19px; box-shadow:0 3px 9px color-mix(in srgb,var(--accent) 14%,transparent); }footer .primary:disabled { box-shadow:none; }.channel-results { padding:0 28px 14px; margin-left:16px; font-size:12px; line-height:1.7; overflow-wrap:anywhere; }
@media(max-width:700px) { .channel-message-overlay { padding:10px; }.channel-message-dialog { max-height:95dvh; border-radius:17px; }header { padding:19px 18px; gap:8px; }.compose-emblem { width:38px; height:38px; border-radius:12px; }.compose-heading { gap:10px; }.compose-heading h2 { font-size:15px; }.compose-heading p { font-size:10px; }.compose-columns { grid-template-columns:1fr; gap:22px; }fieldset { padding:18px; }.channel-to { padding:14px; }.channel-recipients { min-height:0; max-height:175px; }.recipients-empty { padding:18px 8px; }.recipients-empty > span { width:42px; height:42px; margin-bottom:10px; }.recipient-heading { margin-bottom:12px; }.channel-options { gap:6px; }.channel-options button { flex:1; min-width:0; padding:10px 9px; }.message-body-field textarea { min-height:180px; }footer { padding:15px 18px; gap:8px; }footer button { padding:10px 12px; }footer .primary { padding-inline:12px; }.send-summary { flex:1; }.channel-error { margin-inline:18px; } }
.channel-select-all,.channel-recipients > label { flex-direction:row; }.message-body-field { grid-template-rows:auto minmax(205px,1fr); align-content:start; }footer { position:sticky; bottom:0; z-index:1; background:var(--surface); }
@media(prefers-reduced-motion:reduce) { input,textarea,select,.channel-options button { transition:none; } }
.channel-message-overlay.embedded { position:static; display:flex; flex:1; min-width:0; min-height:0; padding:0; background:transparent; backdrop-filter:none; }
.embedded .channel-message-dialog,.embedded .channel-message-dialog.group-compose { width:100%; max-height:none; min-width:0; flex:1; border:0; border-radius:0; box-shadow:none; }
.embedded fieldset { flex:1; padding:18px; }
.embedded .compose-columns { grid-template-columns:minmax(0,1fr); gap:18px; }
.embedded .channel-recipients { min-height:0; max-height:180px; }
.embedded header { padding:18px; }
.embedded .compose-heading h2 { font-size:16px; }
.embedded .compose-emblem { width:34px; height:34px; }
.embedded .channel-message-panel { flex:1; }
.embedded footer { padding:16px 18px; }
.embedded .channel-message-dialog { overflow-y:auto; }
</style>
