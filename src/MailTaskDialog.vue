<script setup>
import { computed, onMounted, ref } from 'vue'
import { CheckSquare, Mail, X } from 'lucide-vue-next'
import { isEmailMessage, isSpamMessage } from './unifiedMail.js'

const props = defineProps({ api: Function, message: Object, currentUser: Object, smtpConfigured: Boolean })
const emit = defineEmits(['close', 'created', 'completed'])
const users = ref([]), loading = ref(true), busy = ref(false), error = ref('')
const savedTask = ref(null), confirmationDraft = ref(null)
const draft = ref({ title: (props.message.subject || 'Zadanie z wiadomości').slice(0, 200),
  description: (props.message.content || '').slice(0, 5000), assignee_id: props.currentUser?.id || '', due_at: '' })
const recipient = computed(() => isEmailMessage(props.message) && !isSpamMessage(props.message)
  && !['sent', 'drafts'].includes(props.message.folder) ? props.message.sender_email : '')
const canSubmit = computed(() => !loading.value && !busy.value && (savedTask.value ||
  (draft.value.title.trim() && draft.value.description.trim() && draft.value.assignee_id && draft.value.due_at)))

async function loadUsers() {
  loading.value = true; error.value = ''
  try {
    const options = await props.api('/sharing-options')
    users.value = [...new Map([props.currentUser, ...options.users].filter(Boolean).map(user => [user.id, user])).values()]
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}
function close() { if (!busy.value) emit('close') }
function confirmation() {
  const task = savedTask.value
  const due = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(task.due_at))
  return { recipient: recipient.value,
    subject: `Re: ${props.message.subject || task.title}`.replace(/[\r\n]/g, ' ').slice(0, 200),
    content: `Dzień dobry,\n\npotwierdzamy, że zadanie zostało przekazane do realizacji.\n\nZadanie: ${task.title}\nTreść: ${task.description}\nTermin realizacji: ${due}` }
}
async function create() {
  if (!canSubmit.value) return
  busy.value = true; error.value = ''
  try {
    if (!savedTask.value) {
      const due = new Date(draft.value.due_at)
      if (!Number.isFinite(due.getTime())) throw new Error('Podaj prawidłowy termin realizacji.')
      savedTask.value = await props.api('/tasks', 'POST', { title: draft.value.title.trim(),
        description: draft.value.description.trim(), assignee_id: draft.value.assignee_id,
        kind: 'general', due_at: due.toISOString(), source_mail_id: recipient.value ? props.message.id : null,
        source_message_id: !isEmailMessage(props.message) ? props.message.center.id : null })
      emit('created', savedTask.value)
    }
    if (recipient.value) {
      if (!confirmationDraft.value) confirmationDraft.value = await props.api('/client-mail/drafts', 'POST', confirmation())
      else {
        const messages = await props.api(`/client-mail?hours=24&include_id=${encodeURIComponent(confirmationDraft.value.id)}`)
        const current = messages.find(message => message.id === confirmationDraft.value.id)
        if (!current) throw new Error('Nie znaleziono szkicu potwierdzenia. Sprawdź folder Robocze.')
        confirmationDraft.value = current
      }
      if (confirmationDraft.value.folder !== 'sent') {
        confirmationDraft.value = await props.api(`/client-mail/${confirmationDraft.value.id}/send`, 'POST',
          { version: confirmationDraft.value.version })
      }
    }
    emit('completed', recipient.value ? 'Zadanie przekazano do realizacji. Potwierdzenie e-mail zostało wysłane do nadawcy.'
      : 'Zadanie przekazano do realizacji.')
    emit('close')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(loadUsers)
</script>

<template>
  <div class="mail-task-overlay" @keydown.esc.stop.prevent="close" @click.self="close">
    <form class="mail-task-dialog" role="dialog" aria-modal="true" aria-labelledby="mail-task-title" @submit.prevent="create">
      <header><h2 id="mail-task-title"><CheckSquare :size="21" />Dodaj zadanie</h2><button type="button" :disabled="busy" aria-label="Zamknij dodawanie zadania" title="Zamknij" @click="close"><X :size="20" /></button></header>
      <p class="mail-task-source">Z wiadomości: <strong>{{ message.subject || '(bez tematu)' }}</strong></p>
      <p v-if="error" class="mail-task-error" role="alert">{{ error }}</p>
      <p v-if="savedTask" class="mail-task-saved" role="status">Zadanie zostało zapisane. Potwierdzenie e-mail nie zostało jeszcze wysłane. {{ confirmationDraft ? 'Ponów wysyłkę lub wróć do niej w folderze „Robocze”.' : 'Ponów wysyłkę, aby utworzyć i wysłać potwierdzenie.' }}</p>
      <p v-if="loading" role="status">Wczytywanie wykonawców…</p>
      <fieldset :disabled="busy || loading || !!savedTask">
        <label>Tytuł zadania<input v-model="draft.title" required maxlength="200" /></label>
        <label>Treść<textarea v-model="draft.description" rows="6" required maxlength="5000" /></label>
        <div class="mail-task-fields"><label>Wykonawca<select v-model="draft.assignee_id" required><option disabled value="">Wybierz osobę</option><option v-for="user in users" :key="user.id" :value="user.id">{{ user.name }}</option></select></label>
        <label>Czas realizacji (termin)<input v-model="draft.due_at" type="datetime-local" required /></label></div>
      </fieldset>
      <div v-if="recipient" class="mail-task-confirmation"><Mail :size="18" /><div>Potwierdzenie przekazania do realizacji otrzyma:<strong>{{ recipient }}</strong><small v-if="!smtpConfigured">Wysyłka wymaga skonfigurowanej poczty SMTP. W razie błędu potwierdzenie pozostanie w Roboczych.</small></div></div>
      <p v-else class="mail-task-source">Ta wiadomość nie ma adresu e-mail nadawcy. Zadanie zostanie zapisane bez potwierdzenia e-mail.</p>
      <footer><button type="button" :disabled="busy" @click="close">{{ savedTask ? 'Zamknij' : 'Anuluj' }}</button><button type="submit" class="primary" :disabled="!canSubmit"><CheckSquare :size="17" />{{ busy ? 'Zapisywanie…' : savedTask ? 'Ponów wysyłkę e-mail' : 'Przekaż do realizacji' }}</button></footer>
    </form>
  </div>
</template>

<style scoped>
.mail-task-overlay { position:fixed; inset:0; z-index:110; display:grid; place-items:center; padding:20px; background:#13213966; backdrop-filter:blur(5px); }
.mail-task-dialog { display:grid; gap:18px; width:min(620px,100%); max-height:90dvh; overflow:auto; padding:26px; border:1px solid var(--border); border-radius:18px; background:var(--surface); box-shadow:0 25px 80px #0003; }
header,header h2,footer { display:flex; align-items:center; gap:10px; }header { justify-content:space-between; }h2 { margin:0; font-size:19px; }header button { padding:6px; background:transparent; border:0; }
p { margin:0; font-size:13px; line-height:1.6; }.mail-task-source { color:var(--secondary); overflow-wrap:anywhere; }
fieldset { display:grid; gap:16px; min-width:0; margin:0; padding:0; border:0; }label { display:grid; gap:7px; min-width:0; font-size:13px; }
input,textarea,select { box-sizing:border-box; min-width:0; width:100%; padding:10px 12px; border:1px solid var(--border); border-radius:9px; color:var(--text); background:var(--surface); font:inherit; }textarea { resize:vertical; }
.mail-task-fields { display:grid; grid-template-columns:1fr 1fr; gap:14px; }.mail-task-confirmation { display:flex; align-items:flex-start; gap:10px; padding:13px; background:var(--accent-soft); border-radius:10px; font-size:12px; line-height:1.6; }.mail-task-confirmation svg { flex-shrink:0; margin-top:2px; }.mail-task-confirmation strong,.mail-task-confirmation small { display:block; overflow-wrap:anywhere; }.mail-task-confirmation small { color:var(--secondary); margin-top:5px; }
.mail-task-error,.mail-task-saved { padding:12px; border-radius:9px; }.mail-task-error { color:var(--theme-danger,#ba253b); background:color-mix(in srgb,#ff637d 10%,var(--surface)); }.mail-task-saved { background:var(--accent-soft); }
footer { justify-content:flex-end; flex-wrap:wrap; }footer button { display:inline-flex; align-items:center; gap:7px; padding:10px 14px; }
@media(max-width:650px) { .mail-task-overlay { padding:10px; }.mail-task-dialog { padding:20px; max-height:94dvh; }.mail-task-fields { grid-template-columns:1fr; } }
</style>
