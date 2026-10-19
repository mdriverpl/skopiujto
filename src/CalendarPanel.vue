<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { CalendarDays, ChevronLeft, ChevronRight, RefreshCw, Plus, ArrowUpRight, ListTodo, Clock3 } from 'lucide-vue-next'
import { dateKey, monthDays } from './calendarDates.js'
const props = defineProps({ api: Function, documents: Array, folders: Array })
const emit = defineEmits(['loaded', 'open-tasks', 'open-document', 'open-folder', 'new-task'])
const today = dateKey(new Date())
const [initialYear, initialMonth] = today.split('-').map(Number)
const year = ref(initialYear), month = ref(initialMonth - 1), selected = ref(today)
const data = ref({ mine: [], sent: [], waiting: 0 }), loading = ref(true), refreshing = ref(false), error = ref(''), showFinished = ref(false)
const pending = item => ['todo', 'in_progress', 'waiting', 'sending'].includes(item.status)
const view = ref('calendar')
try {
  const saved = localStorage.getItem('edokumenty-calendar-view')
  if (['calendar', 'list'].includes(saved)) view.value = saved
} catch {}
function changeView(value) {
  if (!['calendar', 'list'].includes(value)) return
  view.value = value
  try { localStorage.setItem('edokumenty-calendar-view', value) } catch {}
}
const deadline = item => item.due_at && dateKey(item.due_at) ? new Date(item.due_at).getTime() : Infinity
const todoTasks = computed(() => data.value.mine.filter(pending).slice().sort((a, b) => deadline(a) - deadline(b)))
const fullDate = value => new Intl.DateTimeFormat('pl-PL', { timeZone: 'Europe/Warsaw', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

const tasks = computed(() => data.value.mine.filter(item => showFinished.value || pending(item)))
const undated = computed(() => tasks.value.filter(item => !item.due_at || !dateKey(item.due_at)))
const byDay = computed(() => {
  const map = new Map()
  for (const item of tasks.value) {
    if (!item.due_at) continue
    const key = dateKey(item.due_at)
    if (!key) continue
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(item)
  }
  for (const list of map.values()) list.sort((a, b) => new Date(a.due_at) - new Date(b.due_at))
  return map
})
const cells = computed(() => monthDays(year.value, month.value))
const selectedTasks = computed(() => byDay.value.get(selected.value) || [])
const monthTitle = computed(() => new Intl.DateTimeFormat('pl-PL', { month: 'long', year: 'numeric' }).format(new Date(year.value, month.value, 1, 12)))
const selectedTitle = computed(() => new Intl.DateTimeFormat('pl-PL', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date(selected.value + 'T12:00:00')))
const time = value => new Intl.DateTimeFormat('pl-PL', { timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
const labels = { todo: 'Do wykonania', in_progress: 'W toku', done: 'Wykonano', cancelled: 'Anulowano', waiting: 'Oczekuje', accepted: 'Zaakceptowano', expired: 'Wygasło', revoked: 'Cofnięto', failed: 'Błąd wysyłki', sending: 'Wysyłanie' }
const keyOf = item => item.key || item.origin + ':' + item.id
const overdue = item => pending(item) && item.due_at && new Date(item.due_at) < new Date()
function choose(key) {
  selected.value = key
  const [y, m] = key.split('-').map(Number)
  year.value = y; month.value = m - 1
}
function moveMonth(offset) {
  const next = new Date(year.value, month.value + offset, 1, 12)
  year.value = next.getFullYear(); month.value = next.getMonth()
  selected.value = year.value + '-' + String(month.value + 1).padStart(2, '0') + '-01'
}
function openResource(item) {
  const doc = props.documents?.find(doc => doc.id === item.document_id)
  if (doc) emit('open-document', doc)
  else if (item.folder_id && props.folders?.some(folder => folder.id === item.folder_id && folder.permissions?.read)) emit('open-folder', item.folder_id)
  else emit('open-tasks')
}
let timer, disposed = false
async function load(silent = false) {
  if (refreshing.value) return
  refreshing.value = true
  if (!silent) error.value = ''
  try {
    const result = await props.api('/tasks')
    if (!disposed) { data.value = result; emit('loaded', result) }
  } catch (err) { if (!disposed && !silent) error.value = err.message }
  finally { if (!disposed) { refreshing.value = false; loading.value = false } }
}
onMounted(() => { load(); timer = setInterval(() => { if (!document.hidden) load(true) }, 15000) })
onBeforeUnmount(() => { disposed = true; clearInterval(timer) })
</script>
<template>
<section class="calendar-panel">
  <header class="calendar-heading page-menu"><Teleport to="#workspace-title"><div><h1><CalendarDays :size="25" /> Terminarz</h1><p>Twoje zadania i terminy w jednym miejscu.</p></div></Teleport><div class="calendar-actions"><div class="layout-switch" role="group" aria-label="Widok terminarza"><button :aria-pressed="view === 'calendar'" @click="changeView('calendar')"><CalendarDays :size="17" /> Kalendarz</button><button :aria-pressed="view === 'list'" @click="changeView('list')"><ListTodo :size="17" /> Lista zadań do wykonania</button></div><button :disabled="refreshing" aria-label="Odśwież terminarz" @click="load()"><RefreshCw :size="16" /></button><button class="primary" @click="emit('new-task')"><Plus :size="16" /> Nowe zadanie</button></div></header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <p v-if="loading" class="muted" role="status">Wczytywanie terminarza…</p>
  <template v-if="view === 'calendar'">
  <div class="calendar-layout">
    <section class="panel month-panel" aria-label="Kalendarz zadań">
      <header class="month-toolbar"><h2 aria-live="polite">{{ monthTitle }}</h2><div><button aria-label="Poprzedni miesiąc" @click="moveMonth(-1)"><ChevronLeft :size="17" /></button><button @click="choose(today)">Dzisiaj</button><button aria-label="Następny miesiąc" @click="moveMonth(1)"><ChevronRight :size="17" /></button></div></header>
      <label class="calendar-filter"><input v-model="showFinished" type="checkbox" /> Pokaż także zakończone i anulowane</label>
      <div class="weekdays" aria-hidden="true"><span v-for="day in ['Pon', 'Wt', 'Śr', 'Czw', 'Pt', 'Sob', 'Nd']" :key="day">{{ day }}</span></div>
      <div class="month-grid"><button v-for="cell in cells" :key="cell.key" class="calendar-day" :class="{ muted: !cell.inMonth, selected: selected === cell.key, today: cell.key === today }" :aria-pressed="selected === cell.key" :aria-current="cell.key === today ? 'date' : undefined" :aria-label="cell.key + ', zadań: ' + (byDay.get(cell.key)?.length || 0)" @click="choose(cell.key)"><span class="day-number">{{ cell.day }}</span><span v-for="item in (byDay.get(cell.key) || []).slice(0, 2)" :key="keyOf(item)" class="day-task" :class="{ overdue: overdue(item), finished: !pending(item) }">{{ item.title }}</span><small v-if="(byDay.get(cell.key)?.length || 0) > 2" class="more-tasks">+{{ byDay.get(cell.key).length - 2 }} więcej</small><span v-if="byDay.get(cell.key)?.length" class="mobile-count">{{ byDay.get(cell.key).length }}</span></button></div>
      <footer class="calendar-legend"><span><i></i> Zadanie z terminem</span><span><i class="late"></i> Po terminie</span><small>Godziny: Europe/Warsaw</small></footer>
    </section>
    <aside class="panel day-panel"><header><span>WYBRANY DZIEŃ</span><h2>{{ selectedTitle }}</h2><small>{{ selectedTasks.length }} zadań</small></header><p v-if="!selectedTasks.length" class="calendar-empty">Na ten dzień nie masz zaplanowanych zadań.</p><article v-for="item in selectedTasks" :key="keyOf(item)" class="agenda-task"><span class="agenda-time" :class="{ overdue: overdue(item) }"><Clock3 :size="13" /> {{ time(item.due_at) }}<template v-if="overdue(item)"> · po terminie</template></span><h3>{{ item.title }}</h3><p v-if="item.description">{{ item.description }}</p><small>{{ labels[item.status] || item.status }}</small><button @click="openResource(item)">Otwórz <ArrowUpRight :size="14" /></button></article><button class="all-tasks" @click="emit('open-tasks')"><ListTodo :size="16" /> Wszystkie moje zadania</button></aside>
  </div>
  <section class="panel undated-panel"><header><h2>Bez terminu <span>{{ undated.length }}</span></h2><p>Te zadania też czekają na Ciebie.</p></header><p v-if="!undated.length" class="calendar-empty">Brak zadań bez terminu.</p><button v-for="item in undated" :key="keyOf(item)" class="undated-task" @click="openResource(item)"><ListTodo :size="17" /><span><strong>{{ item.title }}</strong><small>{{ labels[item.status] || item.status }}</small></span><ArrowUpRight :size="15" /></button></section>
  </template>
  <section v-else class="calendar-todo" aria-label="Lista zadań do wykonania">
    <header class="todo-heading"><div><h2>Do wykonania <span>{{ todoTasks.length }}</span></h2><p>Wszystkie oczekujące zadania, od najbliższego terminu. Zadania bez terminu znajdziesz na końcu.</p></div></header>
    <div v-if="!loading && !todoTasks.length" class="panel todo-empty"><ListTodo :size="32" :stroke-width="1.5" /><h3>Wszystko na bieżąco</h3><p>Nie masz zadań do wykonania.</p></div>
    <article v-for="item in todoTasks" :key="keyOf(item)" class="panel todo-row"><span class="todo-icon" aria-hidden="true"><ListTodo :size="23" :stroke-width="1.5" /></span><div class="todo-details"><h3><button @click="openResource(item)">{{ item.title }}</button></h3><p v-if="item.description">{{ item.description }}</p><small v-if="item.folder_name">Katalog: {{ item.folder_name }}</small><small v-else-if="item.document_title || item.filename">{{ item.filename || item.document_title }}</small></div><div class="todo-deadline" :class="{ overdue: overdue(item) }"><span><Clock3 :size="13" /> {{ deadline(item) !== Infinity ? fullDate(item.due_at) : 'Bez terminu' }}</span><small v-if="overdue(item)">Po terminie</small></div><span class="todo-status" :class="item.status">{{ labels[item.status] || item.status }}</span><button class="todo-open" :aria-label="`Otwórz zadanie: ${item.title}`" @click="openResource(item)">Otwórz <ArrowUpRight :size="15" /></button></article>
  </section>
</section>
</template>
<style scoped>
.calendar-heading,.calendar-actions,.month-toolbar,.month-toolbar > div { display:flex; align-items:center; gap:10px; }
.calendar-heading { justify-content:space-between; flex-wrap:wrap; margin:24px 0; }.calendar-heading h1 { display:flex; gap:10px; align-items:center; font-size:25px; margin:0; }.calendar-heading h1 svg { color:var(--accent); }.calendar-heading p { color:var(--muted); font-size:12px; margin:8px 0 0; }
.calendar-layout { display:grid; grid-template-columns:minmax(0,1fr) 260px; gap:18px; align-items:start; }.month-panel { padding:20px; border-radius:18px; min-width:0; }.month-toolbar { justify-content:space-between; flex-wrap:wrap; margin-bottom:14px; }.month-toolbar h2 { font-size:18px; margin:0; text-transform:capitalize; }.month-toolbar button { padding:8px; font-size:11px; }
.calendar-filter { display:flex; flex-direction:row; align-items:center; gap:7px; font-size:11px; color:var(--muted); margin:0 0 16px; }.calendar-filter input { width:auto; }
.weekdays,.month-grid { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); }.weekdays { color:var(--muted); font-size:10px; text-align:center; padding-bottom:10px; }
.month-grid { gap:4px; }.calendar-day { display:flex; flex-direction:column; justify-content:flex-start; align-items:stretch; min-width:0; min-height:92px; padding:7px; gap:5px; border:1px solid var(--border); border-radius:9px; text-align:left; background:var(--surface); }.calendar-day.muted { background:var(--surface-soft); color:var(--muted); }.calendar-day.selected { border-color:var(--accent); background:var(--accent-soft); }.day-number { font-size:11px; line-height:22px; }.today .day-number { background:var(--accent); color:var(--theme-on-accent,white); border-radius:50%; width:22px; text-align:center; }
.day-task { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:9px; padding:4px; border-radius:4px; background:var(--accent-soft); color:var(--accent); }.day-task.overdue { color:var(--danger); background:var(--surface-soft); }.day-task.finished { opacity:.6; }.more-tasks { font-size:9px; color:var(--muted); }.mobile-count { display:none; }
.calendar-legend { display:flex; flex-wrap:wrap; align-items:center; gap:12px; font-size:10px; color:var(--muted); padding-top:14px; }.calendar-legend span { display:flex; gap:5px; align-items:center; }.calendar-legend i { width:6px; height:6px; background:var(--accent); border-radius:50%; }.calendar-legend .late { background:var(--danger); }
.day-panel { padding:20px; border-radius:18px; }.day-panel header > span { font-size:9px; color:var(--muted); letter-spacing:1px; }.day-panel h2 { font-size:17px; line-height:1.5; margin:8px 0; text-transform:capitalize; }.day-panel header > small { font-size:11px; color:var(--accent); }.agenda-task { padding:16px 0; border-bottom:1px solid var(--border); overflow-wrap:anywhere; }.agenda-time { display:flex; align-items:center; gap:5px; font-size:10px; color:var(--accent); }.agenda-time.overdue { color:var(--danger); }.agenda-task h3 { font-size:13px; margin:8px 0; }.agenda-task p { font-size:11px; color:var(--secondary); line-height:1.6; white-space:pre-wrap; }.agenda-task > small { display:block; color:var(--muted); font-size:10px; margin-bottom:9px; }.agenda-task button,.all-tasks { font-size:11px; }.all-tasks { width:100%; margin-top:18px; }.calendar-empty { color:var(--muted); font-size:12px; line-height:1.7; margin:20px 0; }
.undated-panel { margin-top:18px; padding:20px; border-radius:18px; }.undated-panel h2 { margin:0; font-size:16px; }.undated-panel h2 span { color:var(--accent); font-size:12px; margin-left:5px; }.undated-panel header p { font-size:11px; color:var(--muted); }.undated-task { display:flex; width:100%; text-align:left; gap:12px; justify-content:flex-start; background:transparent; border:0; border-top:1px solid var(--border); border-radius:0; padding:14px 0; }.undated-task > span { flex:1; min-width:0; overflow-wrap:anywhere; }.undated-task strong { font-size:12px; font-weight:500; }.undated-task small { display:block; color:var(--muted); font-size:10px; margin-top:5px; }.undated-task > svg { color:var(--accent); flex-shrink:0; }
@media(max-width:1000px) { .calendar-layout { grid-template-columns:1fr; } }
@media(max-width:580px) { .month-panel { padding:14px 10px; }.month-toolbar h2 { font-size:16px; }.calendar-day { min-height:55px; padding:5px; gap:2px; align-items:center; }.day-task,.more-tasks { display:none; }.mobile-count { display:block; background:var(--accent-soft); color:var(--accent); border-radius:4px; font-size:9px; padding:2px 5px; }.day-panel { padding:18px; } }
.calendar-actions { flex-wrap:wrap; }
.calendar-actions .layout-switch button { font-size:12px; gap:6px; }
.todo-heading { margin:0 0 18px; }
.todo-heading h2 { font-size:18px; margin:0 0 8px; }
.todo-heading h2 span { font-size:11px; color:var(--accent); background:var(--accent-soft); padding:4px 7px; border-radius:6px; margin-left:5px; }
.todo-heading p { font-size:12px; color:var(--muted); line-height:1.6; margin:0; }
.calendar-todo { display:grid; gap:12px; }
.todo-row { display:grid; grid-template-columns:42px minmax(0,1fr) 155px 100px auto; gap:16px; align-items:center; padding:16px; border-radius:12px; }
.todo-icon { display:flex; padding:10px; color:var(--accent); background:var(--accent-soft); border-radius:11px; }
.todo-details { min-width:0; overflow-wrap:anywhere; }
.todo-details h3 { margin:0; font-size:13px; font-weight:500; }
.todo-details h3 button { border:0; padding:0; background:transparent; text-align:left; font:inherit; overflow-wrap:anywhere; }
.todo-details h3 button:hover { color:var(--accent); }
.todo-details p { margin:6px 0; color:var(--secondary); font-size:11px; line-height:1.6; white-space:pre-wrap; display:-webkit-box; -webkit-line-clamp:2; line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.todo-details small { color:var(--muted); font-size:10px; }
.todo-deadline { display:grid; gap:6px; color:var(--secondary); font-size:11px; }
.todo-deadline > span { display:flex; align-items:center; gap:5px; }
.todo-deadline.overdue { color:var(--danger); }
.todo-deadline small { font-size:10px; }
.todo-status { font-size:10px; padding:5px 8px; border-radius:6px; color:var(--warning); background:var(--warning-soft); justify-self:start; }
.todo-status.in_progress { color:var(--accent); background:var(--accent-soft); }
.todo-open { font-size:11px; padding:7px 9px; }
.todo-empty { text-align:center; padding:36px 20px; color:var(--accent); }
.todo-empty h3 { font-size:15px; color:var(--text); }
.todo-empty p { font-size:12px; color:var(--muted); }
@media(max-width:1000px) { .todo-row { grid-template-columns:42px minmax(0,1fr) auto; }.todo-deadline { grid-column:2; }.todo-status { grid-column:3; grid-row:1; }.todo-open { grid-column:3; grid-row:2; } }
@media(max-width:480px) { .calendar-actions { width:100%; }.calendar-actions .layout-switch { max-width:100%; }.calendar-actions .layout-switch button { font-size:11px; padding:7px; }.todo-row { gap:10px; padding:12px; grid-template-columns:34px minmax(0,1fr) auto; }.todo-icon { padding:7px; }.todo-details h3 { font-size:12px; }.todo-deadline { grid-column:1 / 3; font-size:10px; } }
</style>