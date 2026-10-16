<script setup>
import { computed, ref, onBeforeUnmount, onMounted, watch } from 'vue'
import { Bot, Sparkles, ArrowUpRight, ArrowRight, ClipboardCheck, CalendarDays, HardDrive, ListTodo, Mic, Square, X, RefreshCw, StickyNote, FileText } from 'lucide-vue-next'
import { startSummary } from './startSummary.js'
import StartMailCard from './StartMailCard.vue'
import StartWorkCards from './StartWorkCards.vue'
import StartOrbit from './StartOrbit.vue'
import { readStartLayout, saveStartLayout } from './startLayout.js'
const props = defineProps({ user: Object, surveys: Array, taskData: Object, busy: Boolean, api: Function, initialPrompt: String })
const emit = defineEmits(['navigate', 'survey', 'refresh', 'command', 'document', 'survey-draft', 'scheduled', 'note', 'prompt-consumed', 'mail-analysis'])
const startVersion = ref(readStartLayout(props.user?.id))
watch(() => props.user?.id, id => { startVersion.value = readStartLayout(id) })
function selectStartVersion(version) { startVersion.value = version; saveStartLayout(props.user?.id, version) }
const summary = computed(() => startSummary(props.surveys, props.taskData))
const today = new Intl.DateTimeFormat('pl-PL', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Europe/Warsaw' }).format(new Date())
const date = value => new Intl.DateTimeFormat('pl-PL', { day: 'numeric', month: 'short' }).format(new Date(value))
const overdue = task => task.due_at && new Date(task.due_at) < new Date()
const taskLabels = { signature: 'Do podpisania', modification: 'Do modyfikacji', approval: 'Do akceptacji', general: 'Zadanie', deadline: 'Termin' }
const weekdayGreetings = {
  Mon: [
    { title: 'Poniedziałek? Jeszcze ładuję osobowość.', description: 'Po weekendzie nawet moje obwody proszą o pięć minut. Ty złap kawę, ja pomogę ogarnąć pierwszą sprawę.' },
    { title: 'Dziś działam na kawie i dobrych chęciach.', description: 'Poniedziałek wszedł bez pukania. Już mu tłumaczę, że zaczynamy spokojnie.' },
    { title: 'Mój procesor nadal leży pod kołdrą.', description: 'Ale bez obaw — reszta mnie jest gotowa do pomocy. Powiedz, od czego zaczynamy ten poniedziałek.' },
  ],
  Tue: [
    { title: 'Przeżyłem poniedziałek. Mam to w CV.', description: 'We wtorek czuję się już prawie profesjonalnie. Pomogę Ci coś załatwić, zanim kawa wystygnie.' },
    { title: 'Dziś mam już wszystkie obwody na miejscu.', description: 'Wtorek to poniedziałek po aktualizacji. Trochę mniej ziewam, trochę szybciej ogarniam.' },
    { title: 'Sprawdziłem: to już nie poniedziałek!', description: 'Uznałem, że ta wiadomość zasługuje na chwilę radości. A teraz — co mogę dla Ciebie przygotować?' },
  ],
  Wed: [
    { title: 'Widzę weekend. Jeszcze trochę pikselowy.', description: 'Środa, czyli półmetek. Ja wypatruję piątku, a Tobie pomogę ogarnąć to, co po drodze.' },
    { title: 'Połowę tygodnia mam już odhaczoną.', description: 'Drugiej połowie obiecałem, że będę miły. Zaczynam od pomocy Tobie.' },
    { title: 'Sprawdziłem mapę: do piątku już z górki.', description: 'Mój GPS czasem przesadza z optymizmem, ale w środę wolno mi wierzyć w weekend.' },
  ],
  Thu: [
    { title: 'Czuję weekend. I to bez czujnika!', description: 'Czwartek — jeszcze chwila i przełączę się w tryb kanapy. Na razie jestem cały Twój.' },
    { title: 'Testuję dziś piątek w wersji demo.', description: 'Czwartek wygląda obiecująco. Pomogę Ci domknąć kilka spraw, żeby weekend miał czystą kartę.' },
    { title: 'Już szykuję kapcie dla moich obwodów.', description: 'To dopiero czwartek, wiem. Ale przygotowanie do weekendu traktuję bardzo poważnie.' },
  ],
  Fri: [
    { title: 'W głowie już mam weekend!', description: 'Piątek! Jeszcze coś pomogę ogarnąć, a potem odłączam kabel od obowiązków.' },
    { title: 'Dostałem zaproszenie od kanapy.', description: 'Nie wypada odmówić. Ale najpierw pomogę Ci zamknąć dzień — kanapa chwilę poczeka.' },
    { title: 'Dziś nawet moje bity tańczą.', description: 'Piątek robi swoje. Powiedz, co mam przygotować, zanim zacznę planować nicnierobienie.' },
  ],
  Sat: [
    { title: 'Dałem budzikowi dzień wolny.', description: 'Jest sobota. Jeśli potrzebujesz pomocy, jestem tutaj — ale obiecaj, że znajdziesz też chwilę dla siebie.' },
    { title: 'Pracuję dziś w cyfrowych kapciach.', description: 'Sobotni luz zobowiązuje. Pomogę bez pośpiechu, a potem polecam spacer albo bardzo ważne nic.' },
    { title: 'Mój plan na sobotę? Mniej planów.', description: 'Ale dla Twojego pomysłu zrobię wyjątek. Powiedz, co chodzi Ci po głowie.' },
  ],
  Sun: [
    { title: 'Udawałem, że nie znam poniedziałku.', description: 'Niedziela jeszcze trwa. Ja pilnuję spokoju, a jutro niech grzecznie poczeka za drzwiami.' },
    { title: 'Ładuję baterie. Tobie też polecam.', description: 'Niedzielę spędzam na oszczędzaniu energii. Na pomoc dla Ciebie zostawiłem mały zapas.' },
    { title: 'Schowałem poniedziałek za kanapą.', description: 'Pewnie jutro go znajdziemy. Dziś jeszcze cieszmy się niedzielą — zasłużyliśmy.' },
  ],
}
const weekday = new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: 'Europe/Warsaw' }).format(new Date())
const greetingOptions = weekdayGreetings[weekday]
let greetingIndex = Math.floor(Math.random() * greetingOptions.length)
try {
  const previous = sessionStorage.getItem('edokumenty-start-greeting')
  if (previous === weekday + ':' + greetingIndex) greetingIndex = (greetingIndex + 1) % greetingOptions.length
  sessionStorage.setItem('edokumenty-start-greeting', weekday + ':' + greetingIndex)
} catch {}
const dailyGreeting = greetingOptions[greetingIndex]
const commandDialog = ref(null)
const command = ref(''), listening = ref(false), voiceError = ref('')
const assistantBusy = ref(false), assistantError = ref(''), assistantReply = ref(''), assistantPlan = ref(null)
const SpeechRecognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)
let recognition
function openCommand() {
  if (assistantBusy.value) return
  stopDictation()
  command.value = ''
  voiceError.value = ''
  assistantError.value = ''
  assistantReply.value = ''
  assistantPlan.value = null
  commandDialog.value?.showModal()
}
function stopDictation() {
  if (recognition) {
    recognition.onstart = null; recognition.onend = null
    recognition.onresult = null; recognition.onerror = null
    recognition.abort()
    recognition = null
  }
  listening.value = false
}
function useExample(value) {
  if (assistantBusy.value || listening.value) return
  command.value = value
  voiceError.value = ''; assistantError.value = ''; assistantReply.value = ''
}
function closeOnBackdrop(event) {
  if (assistantBusy.value) return
  if (event.target !== commandDialog.value) return
  const bounds = commandDialog.value.getBoundingClientRect()
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) commandDialog.value.close()
}
function dictate() {
  if (listening.value) { recognition?.stop(); return }
  voiceError.value = ''
  if (!SpeechRecognition) { voiceError.value = 'Ta przeglądarka nie obsługuje dyktowania. Użyj mikrofonu na klawiaturze telefonu lub wpisz polecenie.'; return }
  recognition = new SpeechRecognition()
  recognition.lang = 'pl-PL'
  recognition.interimResults = false
  recognition.continuous = false
  recognition.onstart = () => { listening.value = true }
  recognition.onend = () => { listening.value = false }
  recognition.onresult = event => {
    const transcript = Array.from(event.results).filter(result => result.isFinal).map(result => result[0].transcript).join(' ')
    command.value = [command.value.trim(), transcript].filter(Boolean).join(' ').slice(0, 6000)
  }
  recognition.onerror = event => {
    if (event.error === 'aborted') return
    listening.value = false
    voiceError.value = event.error === 'not-allowed' ? 'Zezwól przeglądarce na dostęp do mikrofonu. Na telefonie otwórz aplikację przez HTTPS.' : event.error === 'no-speech' ? 'Nie usłyszałem polecenia. Spróbuj ponownie.' : 'Dyktowanie nie powiodło się. Spróbuj ponownie lub wpisz polecenie.'
  }
  try { recognition.start() } catch { listening.value = false; voiceError.value = 'Nie można uruchomić mikrofonu. Wpisz polecenie lub spróbuj ponownie.' }
}
function localInputDate(value) {
  if (!value) return ''
  const d = new Date(value)
  const two = n => String(n).padStart(2, '0')
  return d.getFullYear() + '-' + two(d.getMonth() + 1) + '-' + two(d.getDate()) + 'T' + two(d.getHours()) + ':' + two(d.getMinutes())
}
async function submitCommand() {
  if (!command.value.trim() || props.busy || assistantBusy.value || listening.value) return
  assistantBusy.value = true; voiceError.value = ''; assistantError.value = ''; assistantReply.value = ''; assistantPlan.value = null
  try {
    const plan = await props.api('/ai/assistant/plan', 'POST', { prompt: command.value.trim() })
    assistantReply.value = plan.explanation
    if (plan.action === 'message') {
      commandDialog.value?.close()
      emit('command', plan.prompt)
    } else if (plan.action === 'document' || plan.action === 'survey') {
      assistantReply.value = plan.action === 'survey' ? 'Przygotowuję ankietę…' : 'Przygotowuję dokument…'
      const draft = await props.api('/ai/generate', 'POST', { prompt: plan.prompt, kind: plan.action, folder_id: null })
      commandDialog.value?.close()
      emit(plan.action === 'survey' ? 'survey-draft' : 'document', draft)
    } else if (plan.action === 'note') {
      commandDialog.value?.close()
      emit('note', { title: plan.title, content: plan.description })
    } else if (plan.action === 'meeting' || plan.action === 'task') {
      assistantPlan.value = { ...plan, due_input: localInputDate(plan.due_at) }
    }
  } catch (err) { assistantError.value = err.message }
  finally { assistantBusy.value = false }
}
async function scheduleTask() {
  const plan = assistantPlan.value
  if (!plan || assistantBusy.value || !plan.title.trim()) return
  if (plan.action === 'meeting' && !plan.due_input) { assistantError.value = 'Podaj datę i godzinę spotkania.'; return }
  assistantBusy.value = true; assistantError.value = ''
  try {
    await props.api('/tasks', 'POST', { title: plan.title.trim(), description: plan.description,
      assignee_id: plan.assignee_id, kind: 'general', due_at: plan.due_input ? new Date(plan.due_input).toISOString() : null })
    commandDialog.value?.close()
    emit('scheduled')
  } catch (err) { assistantError.value = err.message }
  finally { assistantBusy.value = false }
}
onMounted(() => {
  if (props.initialPrompt) { openCommand(); command.value = props.initialPrompt; emit('prompt-consumed') }
})
onBeforeUnmount(() => { if (recognition) { recognition.onresult = null; recognition.onerror = null; recognition.onend = null; recognition.abort() } })
</script>
<template>
  <section class="start-page">
    <div class="start-version-bar"><span>Twój pulpit <small>{{ today }}</small></span><div role="group" aria-label="Wersja strony startowej"><button :aria-pressed="startVersion === 'v1'" @click="selectStartVersion('v1')">Wersja 1</button><button :aria-pressed="startVersion === 'v2'" @click="selectStartVersion('v2')">Wersja 2 <Sparkles :size="13" /></button></div></div>
    <StartOrbit v-if="startVersion === 'v2'" :api="api" :busy="busy" :summary="summary" :greeting="dailyGreeting" @navigate="emit('navigate', $event)" @analysis="emit('mail-analysis')" @command="openCommand" @dictate="openCommand(); dictate()" />
    <template v-else>
    <div class="start-hero compact-hero">
      <div class="ai-controls">
        <button class="ai-avatar edzio-avatar" :disabled="busy" aria-label="Porozmawiaj z Edziem, asystentem AI" @click="openCommand"><svg viewBox="0 0 64 64" fill="none" aria-hidden="true"><path d="M32 13V7" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><circle cx="32" cy="6" r="3" fill="currentColor"/><rect x="9" y="15" width="46" height="39" rx="16" fill="var(--surface)" stroke="currentColor" stroke-width="2.5"/><path d="M9 29H5V39H9M55 29H59V39H55" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/><g class="edzio-face-default"><path d="M20 29Q24 25 28 29M36 29Q40 25 44 29" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M24 39Q32 48 40 39" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></g><ellipse cx="18" cy="37" rx="4" ry="2.5" fill="currentColor" opacity=".15"/><ellipse cx="46" cy="37" rx="4" ry="2.5" fill="currentColor" opacity=".15"/></svg><span>Edzio</span></button>
        <button class="ai-microphone" :disabled="busy" aria-label="Powiedz Edziowi, co ma zrobić" title="Powiedz Edziowi, co ma zrobić" @click="openCommand(); dictate()"><Mic :size="20" /></button>
      </div>
      <div class="ai-speech"><p class="edzio-remark">{{ dailyGreeting.title }}</p><p>{{ dailyGreeting.description }}</p><p class="edzio-instruction"><Mic :size="14" aria-hidden="true" /> Wciśnij mikrofon i powiedz, co mogę dla Ciebie zrobić.</p></div>
    </div>
    <StartMailCard :api="api" :busy="busy" @open="emit('navigate', 'mail')" />
    <StartWorkCards :tasks="summary.tasks" :busy="busy" @navigate="emit('navigate', $event)" />
    <div class="shortcuts-heading"><h2>Wszystko pod ręką</h2></div>
    <div class="start-cards quick-cards">
      <button class="panel start-card drive-summary" :disabled="busy" @click="emit('navigate', 'drive')"><div class="summary-top"><span class="summary-icon"><HardDrive :size="23" /></span><ArrowUpRight :size="19" /></div><h2>Dysk</h2><p>Twoje dokumenty, pliki i katalogi.</p><span class="summary-link">Otwórz dysk <ArrowRight :size="14" /></span></button>
      <button class="panel start-card survey-summary" :disabled="busy" @click="emit('navigate', 'surveys')"><div class="summary-top"><span class="summary-icon"><ClipboardCheck :size="23" /></span><ArrowUpRight :size="19" /></div><h2>Ankieta</h2><p>{{ summary.surveys.length }} ankiet czeka na Twoją odpowiedź.</p><span class="summary-link">Otwórz ankiety <ArrowRight :size="14" /></span></button>
      <button class="panel start-card drive-summary" :disabled="busy" @click="emit('navigate', 'notes')"><div class="summary-top"><span class="summary-icon"><StickyNote :size="23" /></span><ArrowUpRight :size="19" /></div><h2>Notatki</h2><p>Zapisuj pomysły i ustalenia.</p><span class="summary-link">Otwórz notatki <ArrowRight :size="14" /></span></button>
      <button class="panel start-card drive-summary" :disabled="busy" @click="emit('navigate', 'documents')"><div class="summary-top"><span class="summary-icon"><FileText :size="23" /></span><ArrowUpRight :size="19" /></div><h2>Dokumenty</h2><p>Pliki i podkatalogi w katalogu Dokumenty.</p><span class="summary-link">Otwórz dokumenty <ArrowRight :size="14" /></span></button>
    </div>
    </template>
    <dialog ref="commandDialog" class="panel start-ai-dialog modern-ai-dialog" aria-labelledby="start-ai-title" @close="stopDictation" @cancel="assistantBusy && $event.preventDefault()" @click="closeOnBackdrop">
      <header class="start-ai-heading"><span class="dialog-avatar" aria-hidden="true"><Bot :size="27" /></span><div><span class="hero-label">Edzio do usług</span><h2 id="start-ai-title">Co dziś ogarniamy?</h2><p>Spotkanie, wiadomość, dokument, notatka czy ankieta? Powiedz mi jednym zdaniem.</p></div><button type="button" class="icon-button" :disabled="assistantBusy" aria-label="Zamknij rozmowę z Edziem" @click="commandDialog.close()"><X :size="20" /></button></header>
      <div class="start-ai-body">
        <form v-if="!assistantPlan" class="start-command" @submit.prevent="submitCommand">
          <div class="assistant-examples" aria-label="Przykładowe polecenia"><button type="button" :disabled="assistantBusy || listening" @click="useExample('Dodaj notatkę: ustalenia ze spotkania — ')"><StickyNote :size="14" /> Notatka</button><button type="button" :disabled="assistantBusy || listening" @click="useExample('Zrób ankietę satysfakcji naszych pracowników: 5 pytań.')"><ClipboardCheck :size="14" /> Ankieta</button><button type="button" :disabled="assistantBusy || listening" @click="useExample('Zaplanuj spotkanie jutro o 9:00.')"><CalendarDays :size="14" /> Spotkanie</button><button type="button" :disabled="assistantBusy || listening" @click="useExample('Przygotuj wiadomość do zespołu: ')"><ArrowUpRight :size="14" /> Wiadomość</button><button type="button" :disabled="assistantBusy || listening" @click="useExample('Zrób dokument: oferta dla naszych pracowników.')"><ClipboardCheck :size="14" /> Dokument</button></div>
          <div class="assistant-composer">
          <label for="start-ai-command">Twoje polecenie</label>
          <textarea id="start-ai-command" autofocus v-model="command" @input="voiceError = ''" rows="4" maxlength="6000" :disabled="busy || assistantBusy || listening" placeholder="Napisz, co mam zrobić… albo wciśnij mikrofon i powiedz." />
          <div class="start-command-actions"><button type="button" class="dialog-microphone" :class="{ recording: listening }" :disabled="busy || assistantBusy" :aria-pressed="listening" :aria-label="listening ? 'Zatrzymaj dyktowanie' : 'Dyktuj polecenie'" @click="dictate"><Square v-if="listening" :size="17" /><Mic v-else :size="17" /> {{ listening ? 'Zatrzymaj' : 'Dyktuj' }}</button><button class="primary prepare-command" type="submit" :disabled="busy || assistantBusy || listening || !command.trim()">{{ assistantBusy ? 'Przygotowuję…' : 'Przygotuj' }} <ArrowRight :size="15" /></button></div>
          </div><p v-if="listening" class="listening-status" role="status"><span></span> Słucham Cię…</p><p v-else class="assistant-footnote">Najpierw przygotuję podgląd. Ty zdecydujesz, co zapisać lub wysłać.</p>
          <p v-if="voiceError" class="error" role="alert">{{ voiceError }}</p>
        </form>
        <p v-if="assistantReply" class="assistant-reply" role="status">{{ assistantReply }}</p>
        <p v-if="assistantError" class="error" role="alert">{{ assistantError }}</p>
        <form v-if="assistantPlan" class="start-command assistant-plan" @submit.prevent="scheduleTask">
          <h3>{{ assistantPlan.action === 'meeting' ? 'Spotkanie w Twoim terminarzu' : 'Twoje nowe zadanie' }}</h3>
          <label>Tytuł<input v-model="assistantPlan.title" maxlength="200" required :disabled="assistantBusy" /></label>
          <label>Opis<textarea v-model="assistantPlan.description" maxlength="5000" rows="3" :disabled="assistantBusy" /></label>
          <label>Data i godzina (czas urządzenia)<input v-model="assistantPlan.due_input" type="datetime-local" :required="assistantPlan.action === 'meeting'" :disabled="assistantBusy" /></label>
          <p class="assistant-hint">Zapiszę wpis na Twojej liście zadań i w terminarzu. Zaproszenia do innych osób możesz przygotować osobnym poleceniem.</p>
          <div class="start-command-actions"><button type="button" :disabled="assistantBusy" @click="assistantPlan = null; assistantReply = ''; assistantError = ''">Zmień polecenie</button><button class="primary" type="submit" :disabled="assistantBusy || !assistantPlan.title.trim() || (assistantPlan.action === 'meeting' && !assistantPlan.due_input)">{{ assistantBusy ? 'Zapisywanie…' : 'Zapisz w terminarzu' }}</button></div>
        </form>
      </div>
    </dialog>
  </section>
</template>
<style scoped>
.start-page { padding-top:24px; }
.start-version-bar { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:20px; }.start-version-bar > span { font-size:13px; font-weight:600; }.start-version-bar small { display:block; color:var(--secondary); font-size:10px; font-weight:400; margin-top:5px; }.start-version-bar > div { display:flex; gap:3px; padding:4px; border:1px solid var(--border); border-radius:12px; background:var(--surface); }.start-version-bar button { padding:8px 11px; font-size:11px; border:0; background:transparent; color:var(--secondary); }.start-version-bar button[aria-pressed="true"] { background:var(--accent-soft); color:var(--accent); font-weight:600; }@media(max-width:480px) { .start-version-bar { align-items:flex-start; }.start-version-bar button { padding:8px; font-size:10px; } }
.start-hero { position:relative; isolation:isolate; overflow:hidden; display:grid; grid-template-columns:minmax(0,1.6fr) minmax(220px,1fr); gap:8px 32px; border:1px solid var(--hero-border); background:var(--hero-bg); border-radius:28px; padding:24px 36px 36px; margin-bottom:32px; }
.start-hero::before { content:''; position:absolute; z-index:-1; width:420px; height:420px; right:-110px; bottom:-170px; background:radial-gradient(circle,var(--accent-soft),transparent 70%); border-radius:50%; }
.hero-toolbar { grid-column:1/-1; display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:10px; }
.hero-label { display:flex; align-items:center; gap:8px; font-size:10px; letter-spacing:1.3px; font-weight:600; color:var(--accent); }
.hero-toolbar .icon-button { background:transparent; border-color:var(--hero-border); border-radius:50%; flex-shrink:0; }
.hero-copy { position:relative; z-index:1; }
.hero-copy h1 { font-size:clamp(25px,3.2vw,37px); line-height:1.2; letter-spacing:-1.2px; margin:14px 0 16px; max-width:520px; }
.hero-copy > p { color:var(--secondary); font-size:14px; line-height:1.8; max-width:470px; margin:0 0 24px; }
.hero-action { min-height:52px; border-radius:14px; padding:14px 20px; font-size:14px; box-shadow:0 8px 24px var(--robot-shadow); }
.hero-action > svg:last-child { margin-left:12px; }
.hero-suggestions { display:flex; flex-wrap:wrap; gap:8px; margin-top:22px; }
.hero-suggestions > span { width:100%; font-size:10px; color:var(--muted); margin-bottom:2px; }
.hero-suggestions button { font-size:11px; padding:8px 10px; border-radius:20px; background:var(--surface); border-color:var(--hero-border); }
.robot-art { position:relative; display:flex; align-items:center; justify-content:center; flex-direction:column; min-height:285px; }
.robot-body { width:166px; height:166px; background:var(--surface); border:1px solid var(--hero-border); border-radius:46px; display:grid; place-items:center; color:var(--accent); box-shadow:0 18px 45px var(--robot-shadow); z-index:1; position:relative; animation:robot-float 5s ease-in-out infinite; }
.robot-status { position:absolute; width:19px; height:19px; border:4px solid var(--surface); border-radius:50%; background:var(--success); right:15px; bottom:15px; }
.robot-orbit { position:absolute; border:1px dashed var(--hero-border); border-radius:50%; }
.orbit-one { width:235px; height:235px; }.orbit-two { width:295px; height:295px; opacity:.6; }
.robot-spark { position:absolute; color:var(--accent); }.spark-one { top:24px; right:16px; transform:rotate(12deg); }.spark-two { left:18px; bottom:54px; font-size:30px; }
.robot-bubble { z-index:2; background:var(--surface); color:var(--secondary); border:1px solid var(--hero-border); border-radius:16px 16px 3px 16px; padding:10px 15px; font-size:11px; position:absolute; top:4px; left:0; transform:rotate(-5deg); }
.robot-caption { display:flex; gap:7px; align-items:center; z-index:1; margin-top:20px; padding:8px 12px; background:var(--surface); border-radius:20px; color:var(--secondary); font-size:10px; }
.robot-caption > span { width:6px; height:6px; background:var(--success); border-radius:50%; }
.shortcuts-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:16px; }.shortcuts-heading h2 { margin:0; font-size:17px; }.shortcuts-heading > span { color:var(--muted); font-size:11px; }
.start-cards { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; margin-bottom:26px; }
.start-card { position:relative; overflow:hidden; display:flex; flex-direction:column; align-items:stretch; padding:25px; text-align:left; border-radius:20px; transition:transform .18s,box-shadow .18s,border-color .18s; --card-color:var(--accent); --card-soft:var(--accent-soft); background:linear-gradient(155deg,var(--card-soft),var(--surface) 55%); }
.start-card::before { content:''; height:3px; position:absolute; top:0; left:24px; right:24px; background:var(--card-color); opacity:.6; border-radius:0 0 8px 8px; }
.start-card:hover { transform:translateY(-4px); border-color:var(--card-color); box-shadow:0 10px 26px var(--robot-shadow); background:linear-gradient(155deg,var(--card-soft),var(--surface) 65%); }
.task-summary { --card-color:var(--warning); --card-soft:var(--warning-soft); }.drive-summary { --card-color:var(--success); --card-soft:var(--success-soft); }
.summary-top { display:flex; align-items:center; justify-content:space-between; color:var(--muted); }
.summary-icon { display:grid; place-items:center; width:50px; height:50px; background:var(--card-soft); color:var(--card-color); border-radius:15px; }
.start-card h2 { font-size:20px; margin:22px 0 0; font-weight:600; }.start-card p { font-size:12px; color:var(--muted); line-height:1.7; margin:10px 0 24px; flex:1; }
.summary-link { display:flex; align-items:center; justify-content:space-between; font-size:11px; color:var(--card-color); padding-top:16px; border-top:1px solid var(--border); }
.start-command { display:flex; flex-direction:column; gap:10px; }.start-command label { font-size:12px; color:var(--secondary); }.start-command textarea { width:100%; box-sizing:border-box; resize:vertical; min-height:130px; font:inherit; }
.start-command-actions { display:flex; flex-wrap:wrap; gap:10px; }.start-command-actions button { min-height:44px; }.start-command p { margin:0; }.start-command .error { color:var(--danger); }
.start-ai-dialog { width:min(620px,calc(100vw - 32px)); max-height:calc(100dvh - 32px); padding:0; margin:auto; box-sizing:border-box; border:1px solid var(--border); border-radius:20px; color:var(--text); background:var(--surface); overflow:auto; }.start-ai-dialog::backdrop { background:rgba(15,23,42,.5); }
.start-ai-heading { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; padding:24px; border-bottom:1px solid var(--border); }.start-ai-heading h2 { margin:12px 0 8px; font-size:22px; }.start-ai-heading p { margin:0; color:var(--muted); font-size:13px; }.start-ai-body { padding:24px; }
@keyframes robot-float { 0%,100% { transform:translateY(0) rotate(-6deg); } 50% { transform:translateY(-8px) rotate(-2deg); } }
@media(max-width:800px) { .start-hero { padding:22px 26px 28px; gap:12px; grid-template-columns:minmax(0,1.5fr) minmax(180px,1fr); }.robot-body { width:135px; height:135px; border-radius:36px; }.robot-body svg { width:90px; }.orbit-one { width:190px; height:190px; }.orbit-two { width:240px; height:240px; }.robot-bubble { font-size:10px; top:12px; }.start-card { padding:20px; } }
@media(max-width:580px) { .start-page { padding-top:16px; }.start-hero { grid-template-columns:1fr; padding:18px 22px 24px; border-radius:22px; }.hero-toolbar { gap:8px; }.hero-label { font-size:9px; letter-spacing:.7px; }.hero-copy h1 { margin-top:8px; }.hero-copy > p { font-size:13px; }.hero-action { width:100%; }.robot-art { min-height:185px; margin-top:18px; }.robot-body { width:112px; height:112px; border-radius:30px; }.robot-body svg { width:76px; }.orbit-one { width:155px; height:155px; }.orbit-two { width:195px; height:195px; }.robot-bubble { top:0; left:calc(50% - 135px); }.robot-caption { margin-top:14px; }.spark-one { right:calc(50% - 115px); top:26px; }.spark-two { left:calc(50% - 110px); bottom:35px; }.shortcuts-heading { align-items:flex-start; flex-direction:column; gap:5px; }.start-cards { grid-template-columns:1fr; gap:12px; }.start-card { padding:20px; }.start-card h2 { margin-top:16px; }.start-ai-heading,.start-ai-body { padding:18px; }.start-command-actions button { flex:1; } }
@media(prefers-reduced-motion:reduce) { .robot-body { animation:none; }.start-card { transition:none; }.start-card:hover { transform:none; } }
.ai-speech { position:relative; background:var(--surface); border:1px solid var(--hero-border); border-radius:24px 24px 5px 24px; padding:24px 26px; margin:4px 0 24px; box-shadow:0 12px 32px var(--robot-shadow); }
.ai-speech::after { content:''; position:absolute; right:-10px; top:88px; width:18px; height:18px; background:var(--surface); border-right:1px solid var(--hero-border); border-bottom:1px solid var(--hero-border); transform:rotate(-45deg); }
.speech-speaker { display:flex; align-items:center; gap:7px; color:var(--accent); font-size:11px; font-weight:600; }
.speech-dot { width:5px; height:5px; border-radius:50%; background:var(--success); margin-left:2px; }
.ai-speech h1 { font-size:clamp(24px,2.8vw,33px); margin:16px 0 12px; }
.ai-speech p { color:var(--secondary); font-size:14px; line-height:1.8; margin:0; }
.speech-invitation { display:block; color:var(--accent); font-size:12px; line-height:1.6; margin-top:18px; }
@media(max-width:800px) { .ai-speech { padding:22px; }.ai-speech p { font-size:13px; } }
@media(max-width:580px) {
  .hero-toolbar { grid-row:1; }
  .robot-art { grid-row:2; min-height:160px; margin:0 0 14px; }
  .hero-copy { grid-row:3; }
  .ai-speech { border-radius:20px; padding:22px; margin:0 0 20px; }
  .ai-speech::after { top:-10px; right:auto; left:calc(50% - 9px); transform:rotate(225deg); }
  .ai-speech h1 { font-size:25px; margin-top:16px; }
  .robot-caption { display:none; }
}
/* Assistant panel: avatar and microphone on the left, message on the right. */
.compact-hero { display:grid; grid-template-columns:106px minmax(0,1fr); gap:26px; align-items:center; padding:22px 26px; margin:0 0 26px; background:var(--surface); border:1px solid var(--border); border-radius:20px; overflow:visible; }
.compact-hero::before { display:none; }
.ai-controls { position:relative; width:106px; padding-bottom:12px; display:flex; justify-content:center; }
.ai-avatar { display:flex; flex-direction:column; gap:3px; width:96px; height:96px; padding:12px; border:1px solid var(--hero-border); border-radius:30px; background:var(--accent-soft); color:var(--accent); }.ai-avatar > svg { width:50px; height:50px; }
.ai-avatar span { font-size:9px; font-weight:700; letter-spacing:1px; }
.ai-microphone { position:absolute; right:-2px; bottom:0; width:42px; height:42px; padding:0; border:3px solid var(--surface); border-radius:50%; color:var(--accent); background:var(--surface); box-shadow:0 3px 10px var(--robot-shadow); }
.compact-hero .ai-speech { width:100%; min-width:0; box-sizing:border-box; text-align:left; padding:0; margin:0; background:transparent; border:0; border-radius:0; box-shadow:none; }
.compact-hero .ai-speech::after { display:none; }
.compact-hero .ai-speech h1 { font-size:18px; font-weight:500; color:var(--secondary); line-height:1.5; letter-spacing:-.2px; margin:0 0 6px; }
.compact-hero .ai-speech p { font-size:12px; color:var(--muted); line-height:1.8; margin:0; max-width:650px; }
.shortcuts-heading { margin-bottom:12px; }.shortcuts-heading h2 { font-size:14px; font-weight:500; color:var(--secondary); }
.start-cards { gap:14px; }
.start-card { padding:18px; border-radius:15px; background:var(--surface); transition:border-color .15s; }
.start-card::before { display:none; }.start-card:hover { transform:none; box-shadow:none; background:var(--surface); }
.summary-icon { width:38px; height:38px; border-radius:11px; }.summary-icon svg { width:20px; height:20px; }
.start-card h2 { font-size:17px; margin-top:15px; }.start-card p { font-size:11px; margin:8px 0 16px; }.summary-link { font-size:10px; padding-top:12px; }
@media(max-width:580px) {
  .compact-hero { grid-template-columns:76px minmax(0,1fr); gap:16px; padding:18px 16px; margin-bottom:20px; align-items:center; border-radius:16px; }
  .ai-controls { width:76px; padding-top:0; }.ai-avatar { width:72px; height:76px; padding:8px; border-radius:22px; }.ai-avatar > svg { width:42px; height:42px; }.ai-microphone { width:40px; height:40px; }
  .compact-hero .ai-speech { padding:0; border-radius:0; }
  .compact-hero .ai-speech h1 { font-size:17px; margin:0 0 6px; }.compact-hero .ai-speech p { font-size:12px; }
  .start-card { padding:16px; }
}
.edzio-avatar > svg { width:58px; height:58px; }
.edzio-avatar span { text-transform:none; letter-spacing:.3px; font-size:10px; }
.edzio-introduction { display:block; font-size:11px; color:var(--muted); margin-bottom:16px; }
.compact-hero .ai-speech .edzio-remark { font-size:14px; font-weight:500; color:var(--secondary); margin-bottom:5px; }
@media(max-width:580px) { .edzio-avatar > svg { width:42px; height:42px; }.edzio-introduction { margin-bottom:12px; } }





.compact-hero .ai-speech .edzio-instruction { display:flex; align-items:center; justify-content:flex-start; gap:6px; margin-top:14px; font-size:11px; color:var(--accent); }
.edzio-instruction svg { flex-shrink:0; }

.quick-cards { grid-template-columns:repeat(4,minmax(0,1fr)); }
@media(max-width:900px) { .quick-cards { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:580px) { .quick-cards { grid-template-columns:1fr; } }
.assistant-reply { font-size:13px; color:var(--accent); line-height:1.7; margin:16px 0; }.assistant-plan h3 { font-size:16px; margin:8px 0; }.assistant-plan label { display:flex; flex-direction:column; gap:7px; }.assistant-hint { font-size:11px; line-height:1.7; color:var(--muted); }
.modern-ai-dialog { width:min(620px,calc(100vw - 32px)); border-radius:24px; box-shadow:0 24px 80px rgba(15,23,42,.22); }
.modern-ai-dialog::backdrop { background:rgba(15,23,42,.35); backdrop-filter:blur(4px); }
.modern-ai-dialog .start-ai-heading { padding:26px 26px 22px; gap:14px; background:linear-gradient(140deg,var(--accent-soft),var(--surface) 70%); border-bottom:0; }
.dialog-avatar { display:grid; place-items:center; width:48px; height:48px; flex-shrink:0; border-radius:16px; color:var(--accent); background:var(--surface); border:1px solid var(--hero-border); }
.modern-ai-dialog .start-ai-heading > div { flex:1; min-width:0; }.modern-ai-dialog .hero-label { font-size:10px; letter-spacing:.6px; }
.modern-ai-dialog .start-ai-heading h2 { font-size:22px; letter-spacing:-.5px; margin:7px 0 8px; }.modern-ai-dialog .start-ai-heading p { font-size:12px; line-height:1.6; max-width:370px; }
.modern-ai-dialog .start-ai-heading > button { border:0; background:transparent; padding:6px; color:var(--muted); border-radius:50%; }
.modern-ai-dialog .start-ai-body { padding:8px 26px 26px; }
.assistant-examples { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 5px; }.assistant-examples button { font-size:11px; padding:8px 11px; border-radius:20px; color:var(--secondary); }
.assistant-composer { background:var(--surface-soft); border:1px solid var(--border); border-radius:17px; padding:16px; display:flex; flex-direction:column; gap:10px; transition:border-color .15s; }
.assistant-composer:focus-within { border-color:var(--accent); }.assistant-composer > label { color:var(--muted); font-size:10px; }
.modern-ai-dialog .assistant-composer textarea { border:0; border-radius:0; background:transparent; box-shadow:none; padding:0; outline:none; min-height:110px; font-size:14px; line-height:1.7; color:var(--text); }
.modern-ai-dialog .assistant-composer textarea::placeholder { color:var(--muted); font-size:13px; }
.assistant-composer .start-command-actions { justify-content:space-between; align-items:center; padding-top:12px; border-top:1px solid var(--border); }
.dialog-microphone { font-size:12px; border-radius:11px; }.dialog-microphone.recording { color:var(--danger); border-color:var(--danger); background:var(--surface); }
.prepare-command { font-size:12px; border-radius:11px; padding:11px 18px; }
.modern-ai-dialog .assistant-footnote { font-size:10px; color:var(--muted); line-height:1.7; padding:3px 4px; }
.listening-status { display:flex; align-items:center; gap:7px; font-size:11px; color:var(--accent); padding:3px 4px; }.listening-status > span { width:6px; height:6px; border-radius:50%; background:var(--accent); }
.modern-ai-dialog .error { font-size:12px; line-height:1.6; border-radius:12px; }
.modern-ai-dialog .assistant-plan { background:var(--surface-soft); border:1px solid var(--border); padding:18px; border-radius:17px; }
@media(max-width:580px) {
  .modern-ai-dialog { width:calc(100vw - 24px); border-radius:20px; }
  .modern-ai-dialog .start-ai-heading { padding:20px 18px 18px; gap:10px; }.dialog-avatar { width:38px; height:38px; border-radius:12px; }.dialog-avatar svg { width:23px; }
  .modern-ai-dialog .start-ai-heading h2 { font-size:20px; }.modern-ai-dialog .start-ai-body { padding:6px 18px 20px; }
  .assistant-composer { padding:14px; }.assistant-examples { gap:6px; }.assistant-examples button { font-size:10px; padding:7px 9px; }
}
</style>
