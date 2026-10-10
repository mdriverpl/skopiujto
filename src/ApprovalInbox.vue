<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { CheckCircle2, Download, FileText, RefreshCw, X, Inbox } from 'lucide-vue-next'
const props = defineProps({ api: Function })
const emit = defineEmits(['updated', 'loaded'])
const items = ref([]), loading = ref(true), busy = ref(false), error = ref(''), selected = ref(null), confirmed = ref(false)
const waiting = computed(() => items.value.filter(item => item.status === 'waiting').length)
const labels = { waiting: 'Do akceptacji', accepted: 'Zaakceptowano', expired: 'Wygasło', revoked: 'Cofnięto', failed: 'Błąd wysyłki', sending: 'Wysyłanie' }
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
let timer, disposed = false, refreshing = false
async function load(silent = false) {
  if (refreshing) return
  refreshing = true
  try { const result = await props.api('/approval-inbox'); if (!disposed) { items.value = result; emit('loaded', result) } }
  catch (err) { if (!silent && !disposed) error.value = err.message }
  finally { loading.value = false; refreshing = false }
}
function open(item) { if (!busy.value && item.status === 'waiting') { selected.value = item; confirmed.value = false; error.value = '' } }
async function accept() {
  if (busy.value || !selected.value || !confirmed.value) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api(`/approval-inbox/${selected.value.id}/accept`, 'POST', { confirmed: true })
    items.value = items.value.map(item => item.id === result.id ? result : item)
    selected.value = null; emit('updated')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(() => { load(); timer = setInterval(() => { if (!busy.value) load(true) }, 15000) })
onBeforeUnmount(() => { disposed = true; clearInterval(timer) })
</script>
<template>
  <section class="approval-inbox"><header class="inbox-heading"><div><h1>Do akceptacji <span>{{ waiting }}</span></h1><p>Pliki przesłane bezpośrednio do Ciebie w aplikacji.</p></div><button :disabled="busy || loading" @click="error = ''; load()"><RefreshCw :size="16" /> Odśwież</button></header>
    <p v-if="error && !selected" class="error" role="alert">{{ error }}</p><p v-if="loading" class="muted" role="status">Wczytywanie…</p>
    <div v-else-if="!items.length" class="inbox-empty"><Inbox :size="34" /><h2>Brak otrzymanych plików</h2><p>Gdy ktoś wybierze Cię jako odbiorcę, plik pojawi się tutaj.</p></div>
    <div class="inbox-list"><article v-for="item in items" :key="item.id" class="panel inbox-item"><span class="inbox-icon"><FileText :size="22" /></span><div class="inbox-details"><h2>{{ item.title }}</h2><p>{{ item.filename }} · v{{ item.version }}</p><small>Od: {{ item.sender_name }} · {{ date(item.created_at) }}</small><p v-if="item.message" class="inbox-message">{{ item.message }}</p><small v-if="item.accepted_at">Zaakceptowano {{ date(item.accepted_at) }}</small><small v-else>Ważne do {{ date(item.expires * 1000) }}</small></div><div class="inbox-actions"><span class="inbox-status" :class="item.status">{{ labels[item.status] }}</span><a v-if="['waiting', 'accepted'].includes(item.status) && item.expires * 1000 > Date.now()" :href="`/api/approval-inbox/${item.id}/file`"><Download :size="16" /> Pobierz plik</a><button v-if="item.status === 'waiting'" class="primary" :disabled="busy" @click="open(item)"><CheckCircle2 :size="16" /> Akceptuj</button></div></article></div>
  </section>
  <div v-if="selected" class="modal-backdrop"><section class="panel inbox-confirm" role="dialog" aria-modal="true" aria-labelledby="inbox-confirm-title"><div class="editor-heading"><h2 id="inbox-confirm-title">Akceptacja pliku</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="selected = null"><X :size="20" /></button></div><p><strong>{{ selected.filename }}</strong> · wersja {{ selected.version }}</p><p class="muted">Od: {{ selected.sender_name }}</p><a :href="`/api/approval-inbox/${selected.id}/file`"><Download :size="16" /> Pobierz przesłaną wersję</a><p v-if="error" class="error" role="alert">{{ error }}</p><form @submit.prevent="accept"><label class="check-label"><input v-model="confirmed" type="checkbox" :disabled="busy" required /> Potwierdzam, że zapoznałem/am się z plikiem i akceptuję wersję {{ selected.version }}.</label><div class="editor-actions"><button type="button" :disabled="busy" @click="selected = null">Anuluj</button><button class="primary" type="submit" :disabled="busy || !confirmed"><CheckCircle2 :size="16" /> {{ busy ? 'Zapisywanie…' : 'Akceptuję plik' }}</button></div></form></section></div>
</template>
<style scoped>
.inbox-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; margin: 24px 0; }h1 { margin: 0; font-size: 25px; }h1 span { font-size: 12px; padding: 4px 8px; background: var(--accent-soft); color: var(--accent); border-radius: 8px; vertical-align: middle; }.inbox-heading p { color: var(--muted); font-size: 12px; margin: 8px 0 0; }.inbox-list { display: grid; gap: 14px; }.inbox-item { display: flex; gap: 16px; align-items: flex-start; padding: 20px; border-radius: 14px; }.inbox-icon { background: var(--accent-soft); color: var(--accent); padding: 12px; border-radius: 12px; display: flex; }.inbox-details { flex: 1; min-width: 0; overflow-wrap: anywhere; }.inbox-details h2 { font-size: 15px; margin: 0 0 7px; }.inbox-details p { font-size: 12px; margin: 6px 0; color: var(--secondary); }.inbox-details small { color: var(--muted); font-size: 11px; display: block; margin-top: 6px; }.inbox-message { white-space: pre-wrap; }.inbox-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; font-size: 12px; flex-shrink: 0; }.inbox-actions a, .inbox-confirm a { display: inline-flex; align-items: center; gap: 6px; }.inbox-actions button { font-size: 12px; }.inbox-status { font-size: 11px; padding: 5px 8px; border-radius: 7px; color: var(--muted); background: var(--surface-soft); }.inbox-status.waiting { color: var(--warning); background: var(--warning-soft); }.inbox-status.accepted { color: var(--success); background: var(--success-soft); }.inbox-empty { padding: 50px 20px; text-align: center; color: var(--muted); }.inbox-empty h2 { font-size: 17px; }.inbox-empty p { font-size: 13px; }.inbox-confirm { max-width: 540px; overflow-wrap: anywhere; }.inbox-confirm h2 { font-size: 19px; }.inbox-confirm form { margin-top: 20px; }.inbox-confirm .check-label { align-items: flex-start; line-height: 1.6; font-size: 13px; }.inbox-confirm .check-label input { margin-top: 5px; }@media (max-width: 600px) { .inbox-item { flex-wrap: wrap; gap: 12px; }.inbox-actions { flex-direction: row; align-items: center; justify-content: flex-end; flex-wrap: wrap; width: 100%; }.inbox-heading h1 { font-size: 22px; } }
</style>
