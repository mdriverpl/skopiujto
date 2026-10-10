<script setup>
import { onMounted, ref } from 'vue'
import { ClipboardCheck, Send, CheckCircle2 } from 'lucide-vue-next'
const props = defineProps({ api: Function, token: String })
const survey = ref(null), answers = ref({}), busy = ref(false), error = ref('')
async function load() {
  busy.value = true
  try {
    survey.value = await props.api(`/survey-links/${encodeURIComponent(props.token)}`)
    answers.value = survey.value.answers || Object.fromEntries(survey.value.questions.map(q => [q.id, q.type === 'checkbox' ? false : '']))
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function submit() {
  if (busy.value || !survey.value || survey.value.submitted_at || survey.value.closed_at) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api(`/survey-links/${encodeURIComponent(props.token)}/responses`, 'POST', { answers: answers.value })
    survey.value.submitted_at = result.submitted_at
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <article class="panel public-survey"><span class="public-icon"><ClipboardCheck :size="26" /></span><h1>{{ survey?.title || 'Ankieta' }}</h1><p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="busy && !survey" class="muted">Wczytywanie ankiety…</p><template v-if="survey"><p class="description">{{ survey.description }}</p><p v-if="survey.submitted_at" class="success" role="status"><CheckCircle2 :size="20" /> Dziękujemy! Twoja odpowiedź została zapisana.</p><p v-else-if="survey.closed_at" class="muted">Ankieta została zamknięta.</p><form @submit.prevent="submit"><label v-for="q in survey.questions" :key="q.id" :class="{ checkbox: q.type === 'checkbox' }"><span>{{ q.label }} <small v-if="q.required">*</small></span><textarea v-if="q.type === 'textarea'" v-model="answers[q.id]" :required="q.required" rows="4" maxlength="5000" :disabled="busy || !!survey.submitted_at || !!survey.closed_at" /><select v-else-if="q.type === 'select'" v-model="answers[q.id]" :required="q.required" :disabled="busy || !!survey.submitted_at || !!survey.closed_at"><option value="">Wybierz odpowiedź</option><option v-for="value in q.options" :key="value">{{ value }}</option></select><input v-else-if="q.type === 'checkbox'" v-model="answers[q.id]" type="checkbox" :required="q.required" :disabled="busy || !!survey.submitted_at || !!survey.closed_at" /><input v-else v-model="answers[q.id]" :type="q.type" :step="q.type === 'number' ? 'any' : undefined" :required="q.required" maxlength="5000" :disabled="busy || !!survey.submitted_at || !!survey.closed_at" /></label><footer v-if="!survey.submitted_at && !survey.closed_at"><span>* Pola wymagane</span><button class="primary" type="submit" :disabled="busy"><Send :size="16" /> {{ busy ? 'Zapisywanie…' : 'Wyślij odpowiedź' }}</button></footer></form></template></article>
</template>
<style scoped>
.public-survey { max-width:760px; margin:35px auto; padding:32px; border-radius:20px; }.public-icon { display:grid; place-items:center; width:55px; height:55px; color:var(--accent); background:var(--accent-soft); border-radius:15px; }h1 { font-size:25px; margin:20px 0 10px; }.description { white-space:pre-wrap; overflow-wrap:anywhere; color:var(--muted); font-size:13px; line-height:1.8; margin-bottom:25px; }label { font-size:13px; margin-bottom:20px; }label small { color:var(--danger); }.checkbox { display:flex; flex-direction:row; gap:12px; align-items:center; }.checkbox input { width:16px; height:16px; accent-color:var(--accent); }.success { display:flex; gap:10px; align-items:center; padding:16px; border-radius:12px; background:var(--success-soft); color:var(--success); font-size:13px; }footer { display:flex; gap:14px; align-items:center; justify-content:space-between; border-top:1px solid var(--border); padding-top:20px; }footer span { font-size:11px; color:var(--muted); }@media(max-width:600px) { .public-survey { padding:20px; margin:10px auto; }footer { flex-wrap:wrap; } }
</style>
