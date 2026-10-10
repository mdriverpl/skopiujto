<script setup>
import { ref, onMounted } from 'vue'
import { Download, CheckCircle2 } from 'lucide-vue-next'

const props = defineProps({ token: String, api: Function })
const details = ref(null), error = ref(''), loading = ref(true), busy = ref(false), confirmed = ref(false)
const path = `/approvals/${encodeURIComponent(props.token)}`
const dateTime = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
async function load() {
  loading.value = true; error.value = ''
  try { details.value = await props.api(path) }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}
async function accept() {
  if (!confirmed.value || busy.value) return
  busy.value = true; error.value = ''
  try { details.value = await props.api(path + '/accept', 'POST', { confirmed: true }) }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <article class="panel approval-page">
    <span class="eyebrow">Akceptacja pliku</span>
    <h1>{{ details?.title || 'Plik do akceptacji' }}</h1>
    <p v-if="loading" class="loading">Wczytywanie pliku…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button v-if="error && !details" :disabled="loading" @click="load">Spróbuj ponownie</button>
    <template v-if="details">
      <p class="muted">Od: {{ details.sender_name }} · Dla: {{ details.name || details.phone || details.email }}<span v-if="details.name"> ({{ details.phone || details.email }})</span></p>
      <p><strong>{{ details.filename }}</strong> · wersja {{ details.version }}</p>
      <p v-if="details.message" class="approval-message">{{ details.message }}</p>
      <a class="approval-download" :href="`/api${path}/file`"><Download :size="18" /> Pobierz przesłany plik</a>
      <p class="muted">Link ważny do: {{ dateTime(details.expires * 1000) }}</p>
      <p v-if="details.accepted_at" class="success" role="status"><CheckCircle2 :size="20" /> Zaakceptowano {{ dateTime(details.accepted_at) }}. Nadawca widzi Twoją akceptację.</p>
      <form v-else @submit.prevent="accept"><label class="check-label"><input v-model="confirmed" type="checkbox" :disabled="busy" required /> Potwierdzam, że zapoznałem/am się z przesłanym plikiem i akceptuję wersję {{ details.version }}.</label><button class="primary" :disabled="busy || !confirmed" type="submit"><CheckCircle2 :size="18" /> {{ busy ? 'Zapisywanie…' : 'Akceptuję plik' }}</button></form>
      <p class="muted">Akceptacja zostanie przypisana do {{ details.channel === 'sms' ? 'numeru' : 'adresu' }} {{ details.phone || details.email }}, na który wysłano ten osobisty link.</p>
    </template>
  </article>
</template>

<style scoped>
.approval-page { max-width: 760px; margin: 0 auto; padding: 32px; overflow-wrap: anywhere; }
.approval-message { white-space: pre-wrap; line-height: 1.7; }
.approval-download { display: inline-flex; align-items: center; gap: 8px; padding: 12px 0; }
form { display: flex; flex-direction: column; align-items: flex-start; gap: 20px; margin: 24px 0; }
.success { display: flex; align-items: center; gap: 10px; }
@media (max-width: 600px) { .approval-page { padding: 20px; } }
</style>
