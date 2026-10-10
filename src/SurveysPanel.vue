<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { ClipboardCheck, Plus, X, Trash2, ArrowLeft, RefreshCw, Send, Users, CheckCircle2, BarChart3, Sparkles } from 'lucide-vue-next'
import AiPrompt from './AiPrompt.vue'
import SurveyScore from './SurveyScore.vue'
const props = defineProps({ api: Function, initialSurveyId: String, initialFilter: String })
const emit = defineEmits(['loaded'])
const surveys = ref([]), recipients = ref([]), busy = ref(false), error = ref(''), notice = ref('')
const filter = ref(props.initialFilter || 'all'), search = ref(''), creating = ref(false), current = ref(null), detailTab = ref('form')
const title = ref(''), description = ref(''), questions = ref([]), selected = ref([]), recipientSearch = ref(''), answers = ref({})
const aiDialog = ref(false), aiBusy = ref(false)
const scoringProfile = ref('')
async function newPHQ9() {
  if (busy.value) return
  error.value = ''; busy.value = true
  try {
    const preset = await props.api('/surveys/presets/phq9')
    title.value = preset.title; description.value = preset.description; scoringProfile.value = preset.scoring_profile
    questions.value = preset.questions.map(question => ({ ...question, optionsText: question.options.join('\n') }))
    selected.value = []; creating.value = true
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
const surveyView = ref('list')
function openAi() {
  if (busy.value || aiBusy.value) return
  error.value = ''; notice.value = ''; aiDialog.value = true
}
async function generatedSurvey(draft) {
  await newSurvey()
  title.value = draft.title; description.value = draft.description
  questions.value = draft.questions.map(question => ({ ...question, optionsText: question.options.join('\n') }))
  aiDialog.value = false
}
const sendingSurvey = ref(null), sendChannel = ref('email'), sendPeople = ref([]), sendDays = ref(14), dictionaries = ref([]), selectedDictionary = ref(''), dictionaryContacts = ref([]), chosenContacts = ref([]), dispatchId = ref('')
const availableContacts = computed(() => dictionaryContacts.value.filter(item => item.channels[sendChannel.value]))
async function openSend(item) {
  if (busy.value) return
  sendingSurvey.value = item; error.value = ''; sendPeople.value = [{ name: '', address: '' }]; sendChannel.value = 'email'; selectedDictionary.value = ''; dictionaryContacts.value = []; chosenContacts.value = []; dispatchId.value = crypto.randomUUID()
  busy.value = true
  try { dictionaries.value = await props.api('/dictionaries') } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function loadDictionary() {
  if (busy.value || !selectedDictionary.value) return
  busy.value = true; error.value = ''; dictionaryContacts.value = []; chosenContacts.value = []
  try { dictionaryContacts.value = await props.api(`/messages/contacts?source=dictionaries&dictionary_id=${encodeURIComponent(selectedDictionary.value)}`) }
  catch (err) { error.value = err.message } finally { busy.value = false }
}
function importContacts() {
  const additions = availableContacts.value.filter(item => chosenContacts.value.includes(item.id)).map(item => ({ name: item.name, address: item.channels[sendChannel.value] }))
  const existing = sendPeople.value.filter(item => item.address.trim())
  sendPeople.value = [...new Map([...existing, ...additions].map(item => [item.address.trim(), item])).values()].slice(0, 100)
  chosenContacts.value = []
}
async function sendInvites() {
  if (busy.value || !sendingSurvey.value || !sendPeople.value.length) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api(`/surveys/${sendingSurvey.value.id}/send`, 'POST', { request_id: dispatchId.value, days: sendDays.value,
      recipients: sendPeople.value.map(item => ({ name: item.name, address: item.address, channel: sendChannel.value })) })
    const sent = result.recipients.filter(item => item.status === 'sent').length
    notice.value = `Wysłano: ${sent}. Błędy: ${result.recipients.filter(item => item.status === 'failed').length}. Statusy są w odpowiedziach ankiety.`
    sendingSurvey.value = null; await load()
    if (current.value) current.value = await props.api(`/surveys/${current.value.id}`)
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
const types = { text: 'Krótki tekst', textarea: 'Długi tekst', number: 'Liczba', date: 'Data', select: 'Lista wyboru', checkbox: 'Zaznaczenie' }
const date = value => value ? new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
const visible = computed(() => surveys.value.filter(item => (filter.value === 'all' || (filter.value === 'mine' ? item.assigned : item.is_owner)) && `${item.title} ${item.description}`.toLocaleLowerCase('pl').includes(search.value.trim().toLocaleLowerCase('pl'))))
const totals = computed(() => visible.value.reduce((result, item) => ({ expected: result.expected + item.expected, completed: result.completed + item.completed }), { expected: 0, completed: 0 }))
const people = computed(() => recipients.value.filter(item => item.name.toLocaleLowerCase('pl').includes(recipientSearch.value.trim().toLocaleLowerCase('pl'))))
const canSubmit = computed(() => current.value?.assigned && !current.value.submitted_at && !current.value.closed_at)
let disposed = false, timer, loading = false
async function load() {
  if (loading) return
  loading = true
  try { const data = await props.api('/surveys'); if (!disposed) { surveys.value = data; emit('loaded', data) } }
  catch (err) { if (!disposed) error.value = err.message }
  finally { loading = false }
}
function addQuestion() { questions.value.push({ id: `q_${Date.now()}_${questions.value.length}_${Math.random().toString(36).slice(2,8)}`, label: '', type: 'text', required: true, optionsText: '' }) }
async function newSurvey() {
  if (busy.value) return
  creating.value = true; error.value = ''; title.value = ''; description.value = ''; scoringProfile.value = ''; questions.value = []; selected.value = []; recipientSearch.value = ''; recipients.value = []; addQuestion()
}
async function create() {
  if (busy.value || !title.value.trim() || !questions.value.length) return
  const fields = questions.value.map(q => ({ id: q.id, label: q.label.trim(), type: q.type, required: q.required,
    options: q.type === 'select' ? q.optionsText.split('\n').map(value => value.trim()).filter(Boolean) : [] }))
  if (fields.some(q => !q.label || (q.type === 'select' && (q.options.length < 2 || new Set(q.options).size !== q.options.length)))) { error.value = 'Podaj nazwy pól oraz co najmniej dwie różne opcje dla każdej listy wyboru.'; return }
  busy.value = true; error.value = ''
  try {
    await props.api('/surveys', 'POST', { title: title.value, description: description.value, questions: fields, recipients: selected.value, scoring_profile: scoringProfile.value })
    creating.value = false; notice.value = 'Ankieta została zapisana. Odbiorców możesz wybrać przez „Wyślij do”.'; await load()
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function openSurvey(item) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    current.value = await props.api(`/surveys/${item.id}`)
    const own = current.value.responses.find(response => response.is_me)
    answers.value = current.value.assigned && current.value.submitted_at ? { ...own?.answers } : Object.fromEntries(current.value.questions.map(q => [q.id, q.type === 'checkbox' ? false : '']))
    detailTab.value = current.value.is_owner && !canSubmit.value ? 'responses' : 'form'
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function refreshCurrent() {
  if (busy.value || !current.value) return
  busy.value = true; error.value = ''
  try {
    current.value = await props.api(`/surveys/${current.value.id}`)
    if (current.value.submitted_at) answers.value = { ...current.value.responses.find(item => item.is_me)?.answers }
    await load()
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function submit() {
  if (busy.value || !canSubmit.value) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api(`/surveys/${current.value.id}/responses`, 'POST', { answers: answers.value })
    current.value.submitted_at = result.submitted_at
    current.value.result = result.result || null
    const own = current.value.responses.find(item => item.is_me)
    if (own) { own.answers = { ...answers.value }; own.submitted_at = result.submitted_at }
    notice.value = 'Dziękujemy — odpowiedź została zapisana.'
    current.value = await props.api(`/surveys/${current.value.id}`); await load()
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function deleteSurvey(item) {
  if (busy.value || aiBusy.value || !item?.is_owner) return
  if (!window.confirm(`Usunąć ankietę „${item.title}”? Wszystkie odpowiedzi i wyniki zostaną trwale usunięte, a linki do ankiety przestaną działać.`)) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await props.api(`/surveys/${item.id}`, 'DELETE')
    if (current.value?.id === item.id) { current.value = null; answers.value = {} }
    surveys.value = surveys.value.filter(survey => survey.id !== item.id)
    emit('loaded', surveys.value)
    notice.value = 'Ankieta została usunięta.'
    await load()
  } catch (err) { error.value = err.message } finally { busy.value = false }
}
async function closeSurvey() {
  if (busy.value || !current.value?.is_owner || current.value.closed_at) return
  if (!window.confirm('Zamknąć ankietę? Odbiorcy nie będą mogli wysyłać kolejnych odpowiedzi.')) return
  busy.value = true; error.value = ''
  try { const result = await props.api(`/surveys/${current.value.id}/close`, 'POST'); Object.assign(current.value, result); await load() }
  catch (err) { error.value = err.message } finally { busy.value = false }
}
function distributions(question) {
  const responses = current.value.responses.filter(item => item.submitted_at)
  const values = question.type === 'checkbox' ? [true, false] : question.options
  return values.map(value => ({ label: value === true ? 'Tak' : value === false ? 'Nie' : value,
    count: responses.filter(item => item.answers[question.id] === value).length, total: responses.length }))
}
function showAnswer(value) { return value === true ? 'Tak' : value === false ? 'Nie' : value || '—' }
function showResponseAnswer(response, question) {
  const text = showAnswer(response.answers?.[question.id])
  const item = response.result?.items?.find(item => item.id === question.id)
  return item ? `${text} (${item.points} pkt)` : text
}
onMounted(async () => {
  timer = setInterval(() => { if (!busy.value && !creating.value && !aiDialog.value && !sendingSurvey.value && !current.value) load() }, 15000)
  await load()
  if (!disposed && props.initialSurveyId) await openSurvey({ id: props.initialSurveyId })
})
onBeforeUnmount(() => { disposed = true; clearInterval(timer) })
</script>

<template>
  <section class="surveys">
    <div v-if="aiDialog" class="modal-backdrop" @click.self="!aiBusy && (aiDialog = false)" @keydown.esc="!aiBusy && (aiDialog = false)">
      <section class="panel survey-dialog" role="dialog" aria-modal="true" aria-labelledby="ai-survey-title">
        <header><div><h2 id="ai-survey-title">Ankieta z AI</h2><p>Opisz temat i pytania. Gotową ankietę sprawdzisz przed zapisaniem.</p></div><button class="icon-button" :disabled="aiBusy" aria-label="Zamknij generator ankiety" @click="aiDialog = false"><X :size="20" /></button></header>
        <div class="survey-dialog-body"><AiPrompt :api="api" kind="survey" @busy="aiBusy = $event" @generated="generatedSurvey" /></div>
      </section>
    </div>
    <template v-if="!current">
<header class="survey-heading"><div class="survey-title"><span class="survey-icon"><ClipboardCheck :size="24" /></span><div><h1>Ankiety</h1><p>Zbieraj odpowiedzi i sprawdzaj postęp wypełnienia.</p></div></div><div class="survey-actions"><button :disabled="busy || aiBusy" @click="openAi"><Sparkles :size="17" /> Dodaj z AI</button><button class="primary" :disabled="busy || aiBusy" @click="newSurvey"><Plus :size="17" /> Nowa ankieta</button></div></header>
      <div class="survey-filters">
        <nav class="survey-tabs" aria-label="Widok ankiet">
          <button :disabled="busy || aiBusy" :aria-pressed="surveyView === 'list' && filter === 'all'" @click="surveyView = 'list'; filter = 'all'">Wszystkie</button>
          <button :disabled="busy || aiBusy" :aria-pressed="surveyView === 'list' && filter === 'mine'" @click="surveyView = 'list'; filter = 'mine'">Dla mnie</button>
          <button :disabled="busy || aiBusy" :aria-pressed="surveyView === 'list' && filter === 'sent'" @click="surveyView = 'list'; filter = 'sent'">Utworzone przeze mnie</button>
          <button :disabled="busy || aiBusy" :aria-pressed="surveyView === 'library'" @click="surveyView = 'library'"><ClipboardCheck :size="16" /> Biblioteka ankiet specjalnych</button>
        </nav>
        <input v-show="surveyView === 'list'" v-model="search" aria-label="Szukaj ankiety" placeholder="Szukaj ankiety…" />
      </div>
      <div class="survey-stats"><div><span>Wypełnione</span><strong>{{ totals.completed }}</strong></div><div><span>Oczekiwane odpowiedzi</span><strong>{{ totals.expected }}</strong></div><div><span>Pozostało</span><strong>{{ totals.expected - totals.completed }}</strong></div></div>
    </template>
    <template v-else>
      <button class="survey-back" :disabled="busy" @click="current = null; error = ''; notice = ''"><ArrowLeft :size="16" /> Ankiety</button>
      <header class="survey-heading"><div><h1>{{ current.title }}</h1><p>Autor: {{ current.owner_name }} · {{ date(current.created_at) }}</p></div><div class="survey-actions"><button v-if="current.is_owner && !current.closed_at" :disabled="busy" @click="openSend(current)"><Send :size="16" /> Wyślij do</button><button class="icon-button" :disabled="busy" aria-label="Odśwież odpowiedzi" @click="refreshCurrent"><RefreshCw :size="18" /></button><button v-if="current.is_owner && !current.closed_at" :disabled="busy" @click="closeSurvey">Zamknij ankietę</button><button v-if="current.is_owner" class="survey-delete" :disabled="busy" @click="deleteSurvey(current)"><Trash2 :size="16" /> Usuń ankietę</button><span v-if="current.closed_at" class="survey-badge">Zamknięta</span></div></header><p class="survey-description">{{ current.description }}</p>
      <div class="survey-progress panel"><div><strong>{{ current.completed }} / {{ current.expected }}</strong><span> wypełnionych · pozostało {{ current.expected - current.completed }}</span></div><progress :value="current.completed" :max="current.expected || 1" /></div>
      <nav class="survey-tabs"><button v-if="current.assigned" :aria-pressed="detailTab === 'form'" @click="detailTab = 'form'">{{ current.submitted_at ? 'Moja odpowiedź' : 'Wypełnij ankietę' }}</button><template v-if="current.is_owner"><button :aria-pressed="detailTab === 'responses'" @click="detailTab = 'responses'"><Users :size="16" /> Odpowiedzi</button><button :aria-pressed="detailTab === 'stats'" @click="detailTab = 'stats'"><BarChart3 :size="16" /> Statystyki</button></template></nav>
    </template>
    <p v-if="error && !creating && !sendingSurvey" class="error" role="alert">{{ error }}</p><p v-if="notice" class="survey-notice" role="status">{{ notice }}</p>
    <section v-if="!current && surveyView === 'library'" class="panel special-survey-library">
      <h2>Biblioteka ankiet specjalnych</h2><p>Gotowe formularze ze stałą punktacją. Wynik otrzymuje każda osoba po przesłaniu odpowiedzi.</p>
      <article><h3>Przesiewowa ocena objawów depresji (PHQ-9)</h3><p>9 pytań dotyczących ostatnich 2 tygodni. Każde pytanie: 0–3 punkty. Suma: 0–27 punktów.</p>
        <table><thead><tr><th>Suma punktów</th><th>Nasilenie objawów</th></tr></thead><tbody><tr><td>0–4</td><td>Objawy minimalne</td></tr><tr><td>5–9</td><td>Łagodne</td></tr><tr><td>10–14</td><td>Umiarkowane</td></tr><tr><td>15–19</td><td>Umiarkowanie ciężkie</td></tr><tr><td>20–27</td><td>Ciężkie</td></tr></tbody></table>
        <p class="muted">PHQ-9 to badanie przesiewowe. Wynik nie stanowi diagnozy depresji. Pytania, odpowiedzi i klucz punktacji są stałe. Osobne wyniki są widoczne uczestnikowi i autorowi ankiety.</p>
        <p class="muted">Źródło formularza: <a href="https://projectteachny.org/app/uploads/2022/07/PHQ_Polish-for-Poland.pdf" target="_blank" rel="noopener noreferrer">polska wersja PHQ</a>.</p>
        <button class="primary" :disabled="busy || aiBusy" @click="newPHQ9"><Plus :size="16" /> Utwórz ankietę PHQ-9</button>
      </article>
    </section>
<div v-if="!current" v-show="surveyView === 'list'" class="survey-grid"><article v-for="item in visible" :key="item.id" class="panel survey-card"><div class="survey-card-top"><ClipboardCheck :size="22" /><span class="survey-badge">{{ item.closed_at ? 'Zamknięta' : item.submitted_at ? 'Wypełniona' : item.assigned ? 'Do wypełnienia' : !item.expected ? 'Niewysłana' : 'Aktywna' }}</span></div><h2><button class="survey-open" :disabled="busy" @click="openSurvey(item)">{{ item.title }}</button></h2><p>{{ item.description || `${item.question_count} pól do wypełnienia` }}</p><div class="survey-card-count"><strong>{{ item.completed }} / {{ item.expected }}</strong><span>wypełnionych</span></div><progress :value="item.completed" :max="item.expected || 1" /><button v-if="item.is_owner && !item.closed_at" class="survey-send" :disabled="busy" @click="openSend(item)"><Send :size="15" /> Wyślij do</button><button v-if="item.is_owner" class="survey-delete" :disabled="busy || aiBusy" :aria-label="`Usuń ankietę ${item.title}`" @click="deleteSurvey(item)"><Trash2 :size="15" /></button><footer><span>{{ item.owner_name }}</span><span>{{ date(item.created_at) }}</span></footer></article><p v-if="!visible.length" class="survey-empty">Nie ma jeszcze ankiet w tym widoku.</p></div>
    <form v-else-if="detailTab === 'form' && current.assigned" class="panel response-form" @submit.prevent="submit"><p v-if="current.submitted_at" class="survey-notice"><CheckCircle2 :size="16" /> Odpowiedź wysłana {{ date(current.submitted_at) }}</p><p v-else-if="current.closed_at" class="muted">Ta ankieta została zamknięta.</p><label v-for="question in current.questions" :key="question.id" :class="{ 'survey-check': question.type === 'checkbox' }"><span>{{ question.label }} <small v-if="question.required">*</small></span><textarea v-if="question.type === 'textarea'" v-model="answers[question.id]" rows="4" maxlength="5000" :required="question.required" :disabled="!canSubmit || busy" /><select v-else-if="question.type === 'select'" v-model="answers[question.id]" :required="question.required" :disabled="!canSubmit || busy"><option value="">Wybierz odpowiedź</option><option v-for="value in question.options" :key="value" :value="value">{{ value }}</option></select><input v-else-if="question.type === 'checkbox'" v-model="answers[question.id]" type="checkbox" :required="question.required" :disabled="!canSubmit || busy" /><input v-else v-model="answers[question.id]" :type="question.type" :step="question.type === 'number' ? 'any' : undefined" maxlength="5000" :required="question.required" :disabled="!canSubmit || busy" /></label><footer v-if="canSubmit"><span>* Pola wymagane. Odpowiedź można wysłać jeden raz.</span><button type="submit" class="primary" :disabled="busy"><Send :size="16" /> Wyślij odpowiedź</button></footer></form>
    <div v-else-if="current.is_owner && detailTab === 'responses'" class="panel responses-table" role="region" aria-label="Odbiorcy i odpowiedzi ankiety" tabindex="0"><table><thead><tr><th scope="col">Do kogo</th><th scope="col">Data wysłania</th><th v-if="current.scoring_profile">Wynik PHQ-9</th><th v-for="question in current.questions" :key="question.id" scope="col">{{ question.label }}</th></tr></thead><tbody><tr v-for="response in current.responses" :key="response.user_id"><th scope="row"><strong>{{ response.name }}</strong><small v-if="response.channel">{{ response.channel === 'email' ? 'E-mail' : 'SMS' }}: {{ response.address }}</small><span class="survey-badge" :class="{ completed: response.submitted_at }">{{ response.submitted_at ? 'Wypełniona' : 'Oczekuje na odpowiedź' }}</span><small v-if="response.submitted_at">{{ date(response.submitted_at) }}</small><small v-if="response.channel" :class="{ 'delivery-error': response.status === 'failed' }">{{ response.status === 'sent' ? 'Wysłano' : response.status === 'failed' ? 'Błąd wysyłki' : 'Wysyłka niepotwierdzona' }}<template v-if="response.reason"> — {{ response.reason }}</template></small></th><td class="sent-date">{{ date(response.sent_at) }}</td><td v-if="current.scoring_profile"><template v-if="response.result"><strong>{{ response.result.total }} / 27 pkt</strong><p>{{ response.result.severity }}</p><small v-if="response.result.follow_up_required">Wskazana pilna konsultacja (pytanie 9)</small></template><span v-else>—</span></td><td v-for="question in current.questions" :key="question.id" class="answer-cell">{{ response.submitted_at ? showResponseAnswer(response, question) : '—' }}</td></tr></tbody></table><p v-if="!current.responses.length" class="survey-empty">Ankieta nie ma jeszcze odbiorców. Dodaj ich przez „Wyślij do”.</p></div>
    <div v-else-if="current.is_owner && detailTab === 'stats'" class="response-list"><article v-for="question in current.questions" :key="question.id" class="panel response-card"><h2>{{ question.label }}</h2><p class="muted">{{ current.responses.filter(item => item.submitted_at && item.answers[question.id] !== '' && item.answers[question.id] !== undefined).length }} odpowiedzi</p><div v-if="['select', 'checkbox'].includes(question.type)" class="distribution"><div v-for="entry in distributions(question)" :key="entry.label"><span>{{ entry.label }}</span><progress :value="entry.count" :max="entry.total || 1" /><strong>{{ entry.count }} <small>({{ entry.total ? Math.round(entry.count / entry.total * 100) : 0 }}%)</small></strong></div></div><p v-else class="muted">Treść odpowiedzi znajdziesz w zakładce „Odpowiedzi”.</p></article></div>
    <SurveyScore v-if="current?.result" :result="current.result" />
    <div v-if="creating" class="modal-backdrop" @click.self="!busy && (creating = false)" @keydown.esc="!busy && (creating = false)"><section class="panel survey-dialog" role="dialog" aria-modal="true" aria-labelledby="new-survey-title"><header><div><h2 id="new-survey-title">Nowa ankieta</h2><p>Dodaj pola. Odbiorców wybierzesz później.</p></div><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="creating = false"><X :size="20" /></button></header><form id="survey-create" class="survey-dialog-body" @submit.prevent="create"><p v-if="error" class="error" role="alert">{{ error }}</p><label>Tytuł<input v-model="title" required maxlength="200" :disabled="busy || scoringProfile === 'phq9'" placeholder="Np. Wybór terminu spotkania" /></label><label>Opis<textarea v-model="description" rows="2" maxlength="5000" :disabled="busy || scoringProfile === 'phq9'" placeholder="Krótka instrukcja dla odbiorców" /></label><h3>Pola do wypełnienia</h3><div v-for="(question, index) in questions" :key="question.id" class="question-editor"><div class="question-row"><span class="question-number">{{ index + 1 }}</span><input v-model="question.label" required maxlength="200" aria-label="Nazwa pola" placeholder="Pytanie lub nazwa pola" :disabled="busy || scoringProfile === 'phq9'" /><select v-model="question.type" aria-label="Typ pola" :disabled="busy || scoringProfile === 'phq9'"><option v-for="(label, type) in types" :key="type" :value="type">{{ label }}</option></select><button type="button" class="icon-button" :disabled="busy || scoringProfile === 'phq9' || questions.length === 1" aria-label="Usuń pole" @click="questions.splice(index, 1)"><Trash2 :size="16" /></button></div><label class="survey-check"><input v-model="question.required" type="checkbox" :disabled="busy || scoringProfile === 'phq9'" /> Wymagane</label><label v-if="question.type === 'select'">Opcje — każda w osobnym wierszu<textarea v-model="question.optionsText" required rows="3" :disabled="busy || scoringProfile === 'phq9'" placeholder="Tak&#10;Nie&#10;Nie wiem" /></label></div><button type="button" :disabled="busy || scoringProfile === 'phq9' || questions.length >= 40" @click="addQuestion"><Plus :size="15" /> Dodaj pole</button></form><footer><span>Zapisz teraz, wyślij później.</span><button form="survey-create" type="submit" class="primary" :disabled="busy || !questions.length"><Send :size="16" /> {{ busy ? 'Zapisywanie…' : 'Zapisz ankietę' }}</button></footer></section></div>
    <div v-if="sendingSurvey" class="modal-backdrop" @click.self="!busy && (sendingSurvey = null)"><section class="panel survey-dialog" role="dialog" aria-modal="true" aria-labelledby="send-survey-title"><header><div><h2 id="send-survey-title">Wyślij ankietę</h2><p>{{ sendingSurvey.title }}</p></div><button class="icon-button" :disabled="busy" aria-label="Zamknij" @click="sendingSurvey = null"><X :size="20" /></button></header><form id="survey-send" class="survey-dialog-body" @submit.prevent="sendInvites"><p v-if="error" class="error" role="alert">{{ error }}</p><div class="send-options"><label>Kanał<select v-model="sendChannel" :disabled="busy || sendPeople.some(item => item.address.trim())" @change="chosenContacts = []"><option value="email">E-mail</option><option value="sms">SMS</option></select></label><label>Ważność linku (dni)<input v-model.number="sendDays" type="number" min="1" max="90" required :disabled="busy" /></label></div><p class="muted">Każdy odbiorca otrzyma indywidualny link i będzie mógł odpowiedzieć jeden raz.</p><h3>Załaduj ze słownika</h3><div class="dictionary-load"><select v-model="selectedDictionary" :disabled="busy" aria-label="Wybierz słownik" @change="dictionaryContacts = []; chosenContacts = []"><option value="">Wybierz słownik</option><option v-for="dictionary in dictionaries" :key="dictionary.id" :value="dictionary.id">{{ dictionary.name }}</option></select><button type="button" :disabled="busy || !selectedDictionary" @click="loadDictionary">Załaduj dane</button></div><template v-if="dictionaryContacts.length"><div class="recipient-actions"><button type="button" :disabled="busy" @click="chosenContacts = availableContacts.map(item => item.id)">Zaznacz wszystkie</button><button type="button" :disabled="busy" @click="chosenContacts = []">Wyczyść wybór</button></div><div class="survey-people"><label v-for="contact in availableContacts" :key="contact.id" class="survey-check"><input v-model="chosenContacts" type="checkbox" :value="contact.id" :disabled="busy" /><span>{{ contact.name }} <small>{{ contact.channels[sendChannel] }}</small></span></label><p v-if="!availableContacts.length" class="muted">W tym słowniku nie ma poprawnych danych dla wybranego kanału.</p></div><button type="button" :disabled="busy || !chosenContacts.length" @click="importContacts">Dodaj wybranych odbiorców</button></template><h3>Odbiorcy <small>{{ sendPeople.length }}/100</small></h3><div v-for="(person, index) in sendPeople" :key="index" class="send-person"><input v-model="person.name" maxlength="200" aria-label="Nazwa odbiorcy" placeholder="Imię i nazwisko (opcjonalnie)" :disabled="busy" /><input v-model="person.address" :type="sendChannel === 'email' ? 'email' : 'tel'" :placeholder="sendChannel === 'email' ? 'osoba@firma.pl' : '+48 600 123 456'" aria-label="Adres odbiorcy" required :disabled="busy" /><button class="icon-button" type="button" :disabled="busy" aria-label="Usuń odbiorcę" @click="sendPeople.splice(index, 1)"><Trash2 :size="16" /></button></div><button type="button" :disabled="busy || sendPeople.length >= 100" @click="sendPeople.push({ name: '', address: '' })"><Plus :size="16" /> Dodaj odbiorcę</button></form><footer><span>Zaproszenia zostaną wysłane przez {{ sendChannel === 'email' ? 'e-mail' : 'SMS' }}.</span><button class="primary" form="survey-send" type="submit" :disabled="busy || !sendPeople.length"><Send :size="16" /> {{ busy ? 'Wysyłanie…' : 'Wyślij ankietę' }}</button></footer></section></div>
  </section>
</template>

<style scoped>
.survey-delete { color:var(--danger); }
.special-survey-library { padding:26px; border-radius:16px; margin:20px 0; }.special-survey-library h2 { font-size:20px; }.special-survey-library h3 { font-size:17px; }.special-survey-library p { font-size:13px; line-height:1.8; }.special-survey-library .muted { color:var(--muted); font-size:12px; }.special-survey-library table { width:100%; border-collapse:collapse; font-size:13px; }.special-survey-library th,.special-survey-library td { text-align:left; padding:10px; border-bottom:1px solid var(--border); }
.survey-actions { flex-wrap:wrap; }
.responses-table { margin-top:20px; border-radius:16px; overflow-x:auto; }.responses-table table { width:100%; border-collapse:collapse; text-align:left; }.responses-table thead th { padding:16px 20px; background:var(--surface-soft); color:var(--muted); font-size:11px; font-weight:500; min-width:160px; max-width:300px; overflow-wrap:anywhere; }.responses-table tbody th,.responses-table td { padding:18px 20px; border-top:1px solid var(--border); vertical-align:top; font-size:12px; font-weight:400; }.responses-table tbody th { min-width:220px; max-width:320px; }.responses-table strong { display:block; font-size:13px; font-weight:500; }.responses-table small { display:block; color:var(--muted); font-size:11px; line-height:1.6; margin-top:7px; overflow-wrap:anywhere; }.responses-table .survey-badge { margin-top:10px; }.responses-table .sent-date { color:var(--muted); white-space:nowrap; }.responses-table .answer-cell { min-width:160px; max-width:350px; white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.7; }.responses-table .delivery-error { color:var(--danger); }
.survey-open { border:0; padding:0; background:transparent; color:inherit; font-size:16px; text-align:left; }.survey-send { font-size:12px; margin-top:12px; color:var(--accent); }.send-options { display:grid; grid-template-columns:1fr 1fr; gap:16px; }.send-options label { font-size:12px; }.dictionary-load { display:flex; gap:10px; }.dictionary-load select { flex:1; }.survey-people small { color:var(--muted); display:block; margin-top:4px; }.send-person { display:grid; grid-template-columns:1fr 1.3fr 30px; gap:10px; align-items:center; margin-bottom:12px; }.survey-dialog .muted { font-size:12px; line-height:1.6; }.survey-dialog .survey-people { margin-bottom:12px; }
@media(max-width:650px) { .send-person { grid-template-columns:1fr 30px; }.send-person input:nth-child(2) { grid-column:1; grid-row:2; }.send-person button { grid-column:2; grid-row:1; }.dictionary-load { flex-wrap:wrap; } }
.survey-heading,.survey-title,.survey-actions,.survey-card-top,.survey-filters,.response-card header { display:flex; align-items:center; justify-content:space-between; gap:12px; }.survey-heading { margin:24px 0; }.survey-title { justify-content:flex-start; }.survey-icon { background:var(--accent-soft); color:var(--accent); border-radius:15px; width:54px; height:54px; display:grid; place-items:center; }h1 { margin:0; font-size:26px; }.survey-heading p,.survey-description { color:var(--muted); font-size:12px; line-height:1.7; }.survey-description { white-space:pre-wrap; }.survey-tabs { display:flex; gap:8px; flex-wrap:wrap; }.survey-tabs button { border:0; background:transparent; color:var(--muted); font-size:12px; }.survey-tabs button[aria-pressed=true] { color:var(--accent); background:var(--accent-soft); }.survey-filters { margin-bottom:20px; flex-wrap:wrap; }.survey-filters > input { width:min(320px,100%); }.survey-stats { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-bottom:24px; }.survey-stats > div { padding:18px 22px; background:var(--surface); border:1px solid var(--border); border-radius:14px; }.survey-stats span { display:block; color:var(--muted); font-size:12px; }.survey-stats strong { display:block; margin-top:8px; font-size:25px; }.survey-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:18px; }.survey-card { padding:24px; border-radius:16px; display:block; text-align:left; color:inherit; }.survey-card:hover { border-color:var(--focus-ring); }.survey-card-top { color:var(--accent); }.survey-badge { display:inline-block; background:var(--accent-soft); color:var(--accent); padding:5px 8px; border-radius:6px; font-size:10px; font-weight:400; }.survey-badge.completed { background:var(--success-soft); color:var(--success); }.survey-card h2,.response-card h2 { font-size:16px; margin:18px 0 8px; }.survey-card p { color:var(--muted); font-size:12px; line-height:1.6; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }.survey-card-count { display:flex; gap:8px; align-items:baseline; margin-top:22px; }.survey-card-count strong { font-size:19px; }.survey-card-count span { color:var(--muted); font-size:11px; }progress { display:block; width:100%; height:7px; border:0; border-radius:9px; overflow:hidden; margin:12px 0; background:var(--surface-soft); accent-color:var(--accent); }progress::-webkit-progress-bar { background:var(--surface-soft); }progress::-webkit-progress-value { background:var(--accent); }.survey-card footer { display:flex; justify-content:space-between; gap:10px; border-top:1px solid var(--border); padding-top:14px; margin-top:20px; color:var(--muted); font-size:10px; }.survey-empty { color:var(--muted); font-size:13px; padding:30px; }.survey-notice { color:var(--success); font-size:12px; display:flex; gap:8px; align-items:center; }.survey-back { margin-top:18px; border:0; background:transparent; padding-left:0; font-size:12px; color:var(--accent); }.survey-progress { padding:18px 22px; border-radius:14px; margin-bottom:20px; }.survey-progress span { font-size:12px; color:var(--muted); }.response-form { padding:26px; border-radius:16px; margin-top:20px; max-width:860px; }.response-form label { margin-bottom:20px; font-size:13px; }.response-form small { color:var(--danger); }.response-form footer,.survey-dialog footer { display:flex; justify-content:space-between; align-items:center; gap:14px; }.response-form footer span,.survey-dialog footer span { color:var(--muted); font-size:11px; }.survey-check { display:flex; flex-direction:row; align-items:center; gap:10px; font-size:12px; }.survey-check input { width:16px; height:16px; flex-shrink:0; accent-color:var(--accent); }.response-list { display:grid; gap:14px; margin-top:20px; }.response-card { padding:22px; border-radius:14px; }.response-card header { flex-wrap:wrap; font-size:14px; }.response-card dl { margin:20px 0 0; }.response-card dl > div { padding:12px 0; border-top:1px solid var(--border); }.response-card dt { font-size:11px; color:var(--muted); }.response-card dd { font-size:13px; margin:7px 0 0; white-space:pre-wrap; overflow-wrap:anywhere; }.response-card .muted { font-size:12px; }.distribution > div { display:grid; grid-template-columns:1fr 2fr 80px; gap:15px; align-items:center; font-size:12px; }.distribution small { font-weight:400; color:var(--muted); }.survey-dialog { width:min(850px,100%); max-height:92vh; display:flex; flex-direction:column; overflow:hidden; border-radius:20px; }.survey-dialog > header { display:flex; justify-content:space-between; gap:15px; padding:22px 26px; border-bottom:1px solid var(--border); }.survey-dialog h2 { margin:0; font-size:20px; }.survey-dialog header p { color:var(--muted); font-size:12px; margin:7px 0 0; }.survey-dialog-body { padding:24px 26px; overflow-y:auto; }.survey-dialog-body > label { margin-bottom:18px; font-size:12px; }.survey-dialog h3 { font-size:14px; margin:24px 0 14px; }.survey-dialog h3 small { color:var(--muted); font-size:11px; font-weight:400; margin-left:8px; }.question-editor { background:var(--surface-soft); border:1px solid var(--border); padding:14px; border-radius:12px; margin-bottom:12px; }.question-row { display:grid; grid-template-columns:25px 1fr 165px 30px; gap:10px; align-items:center; }.question-number { color:var(--muted); font-size:12px; }.question-editor .survey-check { margin-top:12px; margin-bottom:0; }.question-editor > label:not(.survey-check) { margin-top:14px; font-size:12px; }.recipient-actions { display:flex; gap:8px; margin:12px 0; }.recipient-actions button { border:0; background:transparent; font-size:11px; color:var(--accent); padding:5px; }.survey-people { max-height:220px; overflow-y:auto; border:1px solid var(--border); border-radius:12px; }.survey-people label { padding:12px 14px; margin:0; border-bottom:1px solid var(--border); }.survey-dialog > footer { padding:18px 26px; border-top:1px solid var(--border); background:var(--surface); }
@media(max-width:650px) { .survey-heading { flex-wrap:wrap; }.survey-stats { gap:8px; }.survey-stats > div { padding:14px 10px; }.survey-stats span { font-size:10px; }.survey-dialog-body { padding:16px; }.question-row { grid-template-columns:20px 1fr 30px; }.question-row select { grid-row:2; grid-column:2; }.question-row button { grid-column:3; grid-row:1; }.survey-dialog footer,.response-form footer { flex-wrap:wrap; }.distribution > div { grid-template-columns:1fr 1fr 65px; } }
</style>
