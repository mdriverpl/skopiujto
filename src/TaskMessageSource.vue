<script setup>
import { computed, ref } from 'vue'
import { Link2, Mail, X } from 'lucide-vue-next'
const props = defineProps({ api: Function, taskId: String, source: Object })
const emit = defineEmits(['open-mail'])
const dialog = ref(null), message = ref(null), loading = ref(false), error = ref('')
const channels = { email: 'E-mail', user: 'Portal pracownika', sms: 'SMS', edelivery: 'eDoręczenia' }
const channel = computed(() => channels[props.source.channel] || 'Inna wiadomość')
function date(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('pl-PL', /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? { dateStyle: 'long' } : { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value))
}
async function open() {
  if (loading.value) return
  loading.value = true; error.value = ''
  try {
    message.value = await props.api(`/tasks/${encodeURIComponent(props.taskId)}/source`)
    dialog.value?.showModal()
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}
function openMailbox() {
  dialog.value?.close()
  emit('open-mail', message.value.mail)
}
</script>

<template>
  <section class="task-message-source" aria-label="Źródło zadania">
    <h3>Źródło wiadomości</h3>
    <button type="button" class="task-source-link" :disabled="loading || !source.available" @click="open"><Link2 :size="18" /><span><strong>{{ channel }}</strong><span>{{ source.title || '(bez tematu)' }}</span></span><span class="task-source-open">{{ loading ? 'Wczytywanie…' : 'Otwórz wiadomość' }}</span></button>
    <p v-if="source.sender" class="task-source-meta">Od: {{ source.sender }}<template v-if="source.created_at"> · {{ date(source.created_at) }}</template></p>
    <p v-if="!source.available" class="task-source-meta">Oryginalna wiadomość nie jest już dostępna.</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <dialog ref="dialog" class="task-source-dialog" aria-labelledby="task-source-title" @click="($event.target === dialog) && dialog.close()">
      <header><h2 id="task-source-title">Wiadomość źródłowa</h2><button type="button" class="icon-button" aria-label="Zamknij wiadomość źródłową" @click="dialog.close()"><X :size="20" /></button></header>
      <div v-if="message" class="task-source-body"><span class="task-source-channel">{{ channel }}</span><h3>{{ message.title || '(bez tematu)' }}</h3><dl><div><dt>Od</dt><dd>{{ message.sender }}<template v-if="message.sender_email && message.sender_email !== message.sender"> &lt;{{ message.sender_email }}&gt;</template></dd></div><div><dt>Do</dt><dd>{{ message.recipient }}</dd></div><div><dt>Data</dt><dd>{{ date(message.created_at) }}</dd></div></dl><p class="task-source-content">{{ message.content || 'Brak treści wiadomości.' }}</p></div>
      <footer><button v-if="message?.mail" type="button" @click="openMailbox"><Mail :size="16" />Otwórz w Centrum wiadomości</button><button type="button" @click="dialog.close()">Zamknij</button></footer>
    </dialog>
  </section>
</template>

<style scoped>
.task-message-source { margin-bottom:24px; }.task-message-source > h3 { font-size:14px; margin:0 0 12px; }
.task-source-link { display:flex; align-items:center; gap:12px; width:100%; padding:14px; text-align:left; color:var(--accent); background:var(--accent-soft); border:1px solid var(--border); border-radius:10px; }
.task-source-link > svg { flex-shrink:0; }.task-source-link > span:first-of-type { display:grid; gap:5px; flex:1; min-width:0; }.task-source-link strong { font-size:11px; }.task-source-link > span > span { font-size:13px; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }.task-source-open { font-size:11px; flex-shrink:0; }.task-source-meta { font-size:11px; color:var(--muted); line-height:1.6; overflow-wrap:anywhere; }
.task-source-dialog { box-sizing:border-box; width:min(740px,calc(100vw - 32px)); max-height:90dvh; padding:0; border:1px solid var(--border); border-radius:18px; background:var(--surface); color:var(--text); box-shadow:0 25px 80px #0003; }.task-source-dialog[open] { display:flex; flex-direction:column; }.task-source-dialog::backdrop { background:#13213966; backdrop-filter:blur(4px); }
.task-source-dialog header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:20px 24px; border-bottom:1px solid var(--border); flex-shrink:0; }.task-source-dialog h2 { font-size:18px; margin:0; }.task-source-body { min-height:0; padding:24px; overflow:auto; }.task-source-channel { display:inline-block; font-size:11px; padding:5px 9px; background:var(--accent-soft); color:var(--accent); border-radius:7px; }.task-source-body h3 { font-size:19px; line-height:1.5; overflow-wrap:anywhere; }.task-source-body dl { display:grid; gap:10px; margin:0 0 24px; font-size:12px; }.task-source-body dl > div { display:flex; gap:12px; }.task-source-body dt { min-width:30px; color:var(--muted); }.task-source-body dd { margin:0; overflow-wrap:anywhere; }.task-source-content { margin:0; white-space:pre-wrap; overflow-wrap:anywhere; font-size:14px; line-height:1.8; }
.task-source-dialog footer { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; padding:16px 24px; border-top:1px solid var(--border); flex-shrink:0; }.task-source-dialog footer button { display:inline-flex; align-items:center; gap:7px; font-size:12px; }
@media(max-width:600px) { .task-source-link { flex-wrap:wrap; }.task-source-open { margin-left:30px; }.task-source-dialog { width:calc(100vw - 20px); max-height:94dvh; }.task-source-dialog header,.task-source-body,.task-source-dialog footer { padding:16px; } }
</style>
