<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { X, Mail, Plus, Trash2, RefreshCw, CheckCircle2, FileText, MessageSquare, Clock3, CircleAlert, ShieldCheck, Send, Users } from 'lucide-vue-next'

const props = defineProps({ file: Object, api: Function })
const emit = defineEmits(['close', 'updated'])
const newRecipient = () => ({ channel: 'email', email: '', name: '', phone: '', user_id: '' })
const recipients = ref([newRecipient()]), message = ref(''), days = ref(7), users = ref([])
const history = ref([]), settings = ref(null), busy = ref(false), loading = ref(true), error = ref(''), notice = ref('')
const tab = ref(props.file.permissions?.send ? 'send' : 'history'), showMessage = ref(false)
const statuses = { accepted: 'Zaakceptowano', waiting: 'Oczekuje', failed: 'Wysyłka niepotwierdzona', expired: 'Link wygasł', revoked: 'Link cofnięty', sending: 'Wysyłanie' }
const statusIcons = { accepted: CheckCircle2, waiting: Clock3, failed: CircleAlert, expired: Clock3, revoked: X, sending: RefreshCw }
const waitingCount = computed(() => history.value.reduce((count, batch) => count + batch.recipients.filter(person => person.status === 'waiting').length, 0))
const acceptedCount = batch => batch.recipients.filter(person => person.accepted_at).length
const address = person => person.channel === 'sms' ? person.phone : person.channel === 'user' ? 'Użytkownik aplikacji' : person.email
const initials = person => (person.name || address(person) || '?').trim().split(/\s+/).slice(0, 2).map(word => word[0]).join('').toUpperCase()
const channelNames = { email: 'E-mail', user: 'Użytkownik', sms: 'SMS' }
const unavailable = computed(() => [...new Set(recipients.value.map(person => person.channel))]
  .filter(channel => settings.value && !settings.value[channel]?.configured).map(channel => settings.value[channel]?.message || `Kanał ${channelNames[channel]} jest niedostępny.`))
const canSend = computed(() => !!settings.value && !unavailable.value.length)
function changeChannel(person) { person.email = ''; person.phone = ''; person.user_id = ''; person.name = '' }
let timer, disposed = false, refreshing = false
const dateTime = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
async function refresh(showError = true) {
  if (refreshing) return
  refreshing = true
  try { history.value = await props.api(`/documents/${props.file.id}/emails`) }
  catch (err) { if (showError) error.value = err.message }
  finally { refreshing = false }
}
async function send() {
  if (busy.value || !canSend.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const response = await props.api(`/documents/${props.file.id}/emails`, 'POST', {
      version: props.file.version, recipients: recipients.value.map(person => ({ channel: person.channel,
        name: person.name.trim(), ...(person.channel === 'email' ? { email: person.email.trim() }
          : person.channel === 'sms' ? { phone: person.phone.trim() } : { user_id: person.user_id }) })), message: message.value, days: days.value
    })
    history.value = response.history
    const batch = history.value.find(item => item.id === response.mailing_id)
    const sent = batch?.recipients.filter(person => person.delivery_status === 'sent').length || 0
    const failed = batch?.recipients.length - sent || 0
    notice.value = `Udostępniono w aplikacji lub przyjęto wysyłkę do ${sent} odbiorców.${failed ? ` Nie potwierdzono wysyłki do ${failed} odbiorców — sprawdź historię.` : ''}`
    tab.value = 'history'
    emit('updated')
  } catch (err) { error.value = err.message; await refresh(false) }
  finally { busy.value = false }
}
async function revoke(person) {
  if (busy.value || !window.confirm(`Cofnąć dostęp do akceptacji dla ${person.name || address(person)}?`)) return
  busy.value = true; error.value = ''
  try { await props.api(`/documents/${props.file.id}/emails/${person.id}/revoke`, 'POST'); await refresh(); emit('updated') }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
function close() { if (!busy.value) emit('close') }
function escape(event) { if (event.key === 'Escape') close() }
onMounted(async () => {
  document.addEventListener('keydown', escape)
  try {
    const results = await Promise.all([props.api('/approval-settings'), props.api(`/documents/${props.file.id}/emails`), props.api('/sharing-options')])
    settings.value = results[0]; history.value = results[1]; users.value = results[2].users
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
  if (!disposed) timer = setInterval(async () => { if (!busy.value) { await refresh(false); if (!disposed) emit('updated') } }, 15000)
})
onBeforeUnmount(() => { disposed = true; clearInterval(timer); document.removeEventListener('keydown', escape) })
</script>

<template>
  <div class="modal-backdrop">
    <section class="panel email-dialog" role="dialog" aria-modal="true" aria-labelledby="email-dialog-title">
      <header class="email-header">
        <div class="heading-mark"><Mail :size="20" /></div>
        <div class="heading-text"><h2 id="email-dialog-title">Udostępnij do akceptacji</h2><p>Wyślij plik i sprawdź odpowiedzi odbiorców.</p></div>
        <button autofocus class="icon-button close-button" :disabled="busy" aria-label="Zamknij okno wysyłki" @click="close"><X :size="20" /></button>
      </header>
      <div class="file-summary"><FileText :size="18" aria-hidden="true" /><span :title="file.filename">{{ file.filename }}</span><span class="version-tag">v{{ file.version }}</span></div>
      <nav class="email-tabs" aria-label="Wysyłanie i akceptacje">
        <button v-if="file.permissions?.send" :class="{ active: tab === 'send' }" :aria-pressed="tab === 'send'" :disabled="busy" @click="tab = 'send'"><Send :size="16" /> Wyślij</button>
        <button :class="{ active: tab === 'history' }" :aria-pressed="tab === 'history'" :disabled="busy" @click="tab = 'history'"><CheckCircle2 :size="17" /> Akceptacje<span v-if="history.length" class="tab-count">{{ history.length }}</span></button>
      </nav>
      <div class="email-content">
        <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="success" role="status">{{ notice }}</p>
        <p v-if="loading" class="loading">Wczytywanie…</p>
        <form v-else-if="tab === 'send' && file.permissions?.send" @submit.prevent="send">
          <p v-for="warning in unavailable" :key="warning" class="error" role="status">{{ warning }}</p>
          <fieldset :disabled="busy" class="recipients-fieldset"><legend>Odbiorcy <span>{{ recipients.length }}/20</span></legend>
            <div v-for="(person, index) in recipients" :key="index" class="recipient-row">
              <label class="recipient-channel">Wyślij przez<select v-model="person.channel" @change="changeChannel(person)"><option value="user">Użytkownik aplikacji</option><option value="email">E-mail</option><option value="sms">SMS</option></select></label>
              <label v-if="person.channel === 'user'" class="recipient-email">Użytkownik<select v-model="person.user_id" required><option disabled value="">Wybierz użytkownika…</option><option v-for="account in users" :key="account.id" :value="account.id">{{ account.name }}</option></select><small v-if="!users.length">Brak innych aktywnych użytkowników.</small></label>
              <label v-else-if="person.channel === 'sms'" class="recipient-email">Numer telefonu<input v-model="person.phone" type="tel" required maxlength="30" autocomplete="off" placeholder="+48 600 123 456" /></label>
              <label v-else class="recipient-email">Adres e-mail<input v-model="person.email" type="email" required maxlength="254" autocomplete="off" placeholder="osoba@firma.pl" /></label>
              <label v-if="person.channel !== 'user'" class="recipient-name">Imię i nazwisko <span class="optional">opcjonalnie</span><input v-model="person.name" maxlength="100" autocomplete="off" placeholder="np. Anna Kowalska" /></label>
              <button class="icon-button remove-recipient" type="button" :disabled="recipients.length === 1" :aria-label="`Usuń odbiorcę ${index + 1}`" title="Usuń odbiorcę" @click="recipients.splice(index, 1)"><Trash2 :size="16" /></button>
            </div>
            <button class="text-button add-recipient" type="button" :disabled="recipients.length >= 20" @click="recipients.push(newRecipient())"><Plus :size="16" /> Dodaj odbiorcę</button>
          </fieldset>
          <div class="send-options"><button class="text-button" type="button" :disabled="busy" :aria-expanded="showMessage" aria-controls="email-message" @click="showMessage = !showMessage"><MessageSquare :size="16" /> {{ showMessage ? 'Ukryj wiadomość' : message ? 'Edytuj wiadomość' : 'Dodaj wiadomość' }}</button><label class="link-validity"><Clock3 :size="15" /> Link ważny<input v-model.number="days" :disabled="busy" type="number" min="1" max="30" required aria-label="Ważność linku w dniach" /><span>dni</span></label></div>
          <label v-if="showMessage" id="email-message" class="message-field">Wiadomość dla odbiorców<textarea v-model="message" :disabled="busy" maxlength="3000" rows="3" placeholder="Napisz, czego dotyczy plik…"></textarea></label>
          <div class="send-footer"><p><ShieldCheck :size="16" /><span>Osobna akceptacja dla każdej osoby. SMS zawiera link; e-mail także załącznik.</span></p><button class="primary" :disabled="busy || !canSend" type="submit"><Send :size="16" /> {{ busy ? 'Wysyłanie…' : 'Wyślij do akceptacji' }}</button></div>
        </form>
        <section v-else-if="!loading" class="approval-history" aria-label="Historia wysyłek i akceptacji">
          <div class="history-heading"><div><h3>Historia akceptacji</h3><p>{{ waitingCount ? `Oczekujące odpowiedzi: ${waitingCount}` : 'Statusy odpowiedzi Twoich odbiorców.' }}</p></div><button class="icon-button" :disabled="busy" aria-label="Odśwież akceptacje" title="Odśwież akceptacje" @click="refresh(); emit('updated')"><RefreshCw :size="17" /></button></div>
          <div v-if="!history.length" class="history-empty"><Users :size="28" /><strong>Jeszcze bez wysyłek</strong><p>Po wysłaniu pliku zobaczysz tutaj odpowiedzi odbiorców.</p></div>
          <article v-for="batch in history" :key="batch.id" class="mailing-batch">
            <header class="batch-heading"><div><strong>Wersja {{ batch.version }}</strong><span v-if="batch.current_version" class="current-tag">obecna</span><small>{{ dateTime(batch.created_at) }}</small></div><span class="batch-progress" :class="{ complete: acceptedCount(batch) === batch.recipients.length }">{{ acceptedCount(batch) }}/{{ batch.recipients.length }} zaakceptowało</span></header>
            <div v-for="person in batch.recipients" :key="person.id" class="approval-person">
              <span class="person-avatar" aria-hidden="true">{{ initials(person) }}</span>
              <div class="person-details"><strong>{{ person.name || address(person) }}</strong><small>{{ channelNames[person.channel || 'email'] }}<template v-if="person.name && person.channel !== 'user'"> · {{ address(person) }}</template></small><small v-if="person.sent_at">Wysłano {{ dateTime(person.sent_at) }}</small></div>
              <div class="person-response"><span class="approval-status" :class="person.status"><component :is="statusIcons[person.status]" :size="14" /> {{ statuses[person.status] }}</span><small v-if="person.accepted_at">{{ dateTime(person.accepted_at) }}</small></div>
              <button v-if="['waiting', 'sending'].includes(person.status)" class="icon-button revoke-button" :disabled="busy" :aria-label="`Cofnij dostęp dla ${person.name || address(person)}`" title="Cofnij dostęp" @click="revoke(person)"><X :size="16" /></button>
              <p v-if="person.error" class="delivery-error">{{ person.error }}</p>
            </div>
            <footer class="batch-expiry"><Clock3 :size="13" /> Linki ważne do {{ dateTime(batch.expires * 1000) }}</footer>
          </article>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.email-dialog { width: 730px; max-width: 100%; max-height: 88vh; display: flex; flex-direction: column; overflow: hidden; border-radius: 18px; box-shadow: 0 24px 90px #25283d26; }
.email-header { display: flex; align-items: center; gap: 12px; padding: 24px 26px 18px; flex-shrink: 0; }
.heading-mark { display: flex; align-items: center; justify-content: center; width: 42px; height: 42px; border-radius: 12px; background: var(--accent-soft); color: var(--accent); flex-shrink: 0; }
.heading-text { flex: 1; min-width: 0; }
.heading-text h2 { margin: 0; font-size: 18px; letter-spacing: -.35px; }
.heading-text p { margin: 5px 0 0; color: var(--muted); font-size: 12px; }
.close-button { align-self: flex-start; color: var(--muted); }
.file-summary { display: flex; align-items: center; gap: 10px; margin: 0 26px 18px; padding: 11px 12px; border-radius: 10px; background: var(--page-bg); color: var(--secondary); flex-shrink: 0; }
.file-summary > svg { flex-shrink: 0; }
.file-summary > span:first-of-type { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); font-size: 13px; font-weight: 500; }
.version-tag { background: var(--surface); border: 1px solid var(--border); padding: 3px 7px; border-radius: 6px; font-size: 11px; flex-shrink: 0; }
.email-tabs { display: flex; gap: 22px; padding: 0 26px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.email-tabs button { position: relative; border: none; border-radius: 0; background: transparent; padding: 11px 0 13px; color: var(--muted); font-size: 13px; font-weight: 500; }
.email-tabs button.active { color: var(--accent); }
.email-tabs button.active::after { content: ''; position: absolute; height: 2px; background: var(--accent); bottom: -1px; left: 0; right: 0; border-radius: 2px; }
.tab-count { padding: 2px 6px; border-radius: 5px; background: var(--accent-soft); color: var(--accent); font-size: 10px; }
.email-content { overflow-y: auto; padding: 24px 26px; min-height: 0; }
.email-content .error, .email-content .success { font-size: 12px; line-height: 1.6; margin: 0 0 18px; padding: 11px 13px; }
form { display: flex; flex-direction: column; gap: 18px; }
.recipients-fieldset { border: none; border-radius: 0; padding: 0; margin: 0; min-width: 0; }
.recipients-fieldset legend { padding: 0; font-size: 13px; font-weight: 600; margin-bottom: 14px; }
.recipients-fieldset legend span { margin-left: 7px; color: var(--theme-muted, #9ca1b2); font-size: 11px; font-weight: 400; }
.recipient-row { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.2fr) 30px; gap: 10px; align-items: end; margin-bottom: 18px; }
.recipient-name { grid-column: 2; }
.recipient-channel { grid-row: 1; }
.remove-recipient { grid-column: 3; grid-row: 1; }
.email-dialog select { min-width: 0; width: 100%; padding: 10px 8px; font-size: 12px; border-color: var(--border); border-radius: 8px; }
.recipient-row label { position: relative; margin: 0; gap: 7px; font-size: 11px; color: var(--secondary); }
.recipient-row .optional { position: absolute; right: 0; top: 0; color: var(--muted); font-size: 10px; }
.email-dialog input, .email-dialog textarea { padding: 10px 11px; border-color: var(--border); font-size: 13px; border-radius: 8px; }
.email-dialog input::placeholder, .email-dialog textarea::placeholder { color: var(--theme-muted, #afb3c1); }
.remove-recipient { padding: 10px 6px; color: var(--theme-muted, #9ca1b2); margin-bottom: 1px; }
.text-button { padding: 5px 0; border: none; color: var(--secondary); background: transparent; font-size: 12px; justify-content: flex-start; }
.text-button:hover { color: var(--accent); background: transparent; }
.add-recipient { color: var(--accent); }
.send-options { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 14px; border-top: 1px solid var(--border); }
.link-validity { display: flex; align-items: center; flex-direction: row; gap: 7px; margin: 0; color: var(--muted); font-size: 12px; white-space: nowrap; }
.link-validity input { width: 57px; padding: 7px 6px; text-align: center; }
.message-field { font-size: 12px; color: var(--secondary); margin: 0; }
.send-footer { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding-top: 6px; }
.send-footer p { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 11px; line-height: 1.6; margin: 0; }
.send-footer p svg { flex-shrink: 0; color: var(--theme-muted, #8e99af); }
.send-footer .primary { font-size: 12px; padding: 11px 15px; border-radius: 9px; white-space: nowrap; box-shadow: 0 3px 8px #6654d91a; }
.history-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.history-heading h3 { margin: 0; font-size: 13px; font-weight: 600; }
.history-heading p { margin: 5px 0 0; color: var(--muted); font-size: 11px; }
.history-heading button { color: var(--muted); }
.history-empty { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 30px 20px; color: var(--theme-muted, #a3a8ba); }
.history-empty strong { color: var(--secondary); font-size: 13px; margin-top: 13px; }
.history-empty p { font-size: 12px; line-height: 1.6; margin: 7px 0 0; }
.mailing-batch { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; margin-top: 14px; }
.batch-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 13px 15px; background: var(--theme-accent-soft, #fafbfe); border-bottom: 1px solid var(--border); }
.batch-heading strong { font-size: 12px; font-weight: 600; }
.current-tag { color: var(--theme-muted, #9a9fb1); font-size: 10px; margin-left: 7px; }
.batch-progress { color: var(--muted); font-size: 11px; text-align: right; }
.batch-progress.complete { color: var(--success); }
.approval-person { display: grid; grid-template-columns: 30px minmax(0, 1fr) auto 24px; align-items: center; gap: 10px; padding: 13px 15px; border-bottom: 1px solid var(--surface-soft); }
.person-avatar { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 50%; background: var(--accent-soft); color: var(--accent); font-size: 10px; font-weight: 600; }
.person-details { min-width: 0; overflow-wrap: anywhere; }
.person-details strong { font-size: 12px; font-weight: 500; }
.person-response { text-align: right; }
small { display: block; color: var(--theme-muted, #9a9fb1); margin-top: 4px; font-size: 10px; }
.approval-status { display: inline-flex; align-items: center; gap: 5px; padding: 5px 7px; background: var(--warning-soft); color: var(--warning); border-radius: 6px; font-size: 10px; }
.revoke-button { padding: 4px; color: var(--muted); }
.revoke-button:hover { color: var(--theme-danger, #a95353); background: var(--danger-soft); }
.batch-expiry { display: flex; align-items: center; gap: 6px; padding: 10px 15px; color: var(--muted); font-size: 10px; }
.delivery-error { grid-column: 2 / -1; font-size: 11px; line-height: 1.6; margin: 0; }
.approval-status.accepted { color: var(--success); background: var(--success-soft); }
.approval-status.failed, .delivery-error { color: var(--danger); }
.approval-status.failed { background: var(--danger-soft); }
.approval-status.revoked, .approval-status.expired { color: var(--secondary); background: var(--border); }
@media (max-width: 600px) {
  .email-dialog { max-height: 92vh; }
  .email-header { padding: 18px 18px 14px; gap: 10px; }
  .heading-text h2 { font-size: 16px; }
  .heading-text p { font-size: 11px; }
  .heading-mark { width: 36px; height: 36px; }
  .file-summary { margin: 0 18px 14px; }
  .email-tabs { padding: 0 18px; }
  .email-content { padding: 20px 18px; }
  .recipient-row { grid-template-columns: minmax(0, 1fr) 30px; }
  .recipient-email { grid-column: 1; }
  .recipient-channel { grid-column: 1; grid-row: 1; }
  .recipient-email { grid-column: 1; grid-row: 2; }
  .recipient-name { grid-column: 1; grid-row: 3; }
  .remove-recipient { grid-column: 2; grid-row: 1; }
  .send-options { flex-wrap: wrap; }
  .send-footer { flex-direction: column; align-items: stretch; gap: 14px; }
  .send-footer .primary { width: 100%; }
  .approval-person { grid-template-columns: 28px minmax(0, 1fr) 24px; gap: 8px; }
  .person-response { grid-column: 2; text-align: left; }
  .revoke-button { grid-column: 3; grid-row: 1; }
  .delivery-error { grid-column: 2 / -1; }
}
</style>
