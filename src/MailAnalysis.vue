<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { Sparkles, Inbox, Send, ShieldCheck, ShieldAlert, Building2, AlertCircle, Reply, CreditCard, FileText, Mail, RefreshCw, ChevronLeft, ChevronRight, ArrowUpRight, Clock3, Search } from 'lucide-vue-next'
import MailDayMessages from './MailDayMessages.vue'

const props = defineProps({ api: Function, initialDay: String, request: Number })
const emit = defineEmits(['day-change', 'open-message', 'open-folder'])
const today = () => new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const day = ref(props.initialDay || today()), report = ref(null), loading = ref(false), error = ref('')
const activeGroup = ref('attention'), search = ref(''), limit = ref(12), messageSection = ref(null)
const categories = {
  correspondence: { name: 'Korespondencja', color: '#7365dc' }, invoice: { name: 'Faktury', color: '#229b86' },
  payment: { name: 'Płatności', color: '#59bca6' }, order: { name: 'Zamówienia', color: '#4e8de3' },
  advertisement: { name: 'Reklamy', color: '#e8ae55' }, newsletter: { name: 'Newslettery', color: '#bc89d8' },
  notification: { name: 'Powiadomienia', color: '#6fb6cf' }, spam: { name: 'Spam', color: '#e17e91' },
  other: { name: 'Inne', color: '#9a9fb3' }, uncategorized: { name: 'Bez kategorii', color: '#cbd0dc' }
}
const folders = [{ id: 'inbox', label: 'Odebrane' }, { id: 'sent', label: 'Wysłane' }, { id: 'archive', label: 'Archiwum' }, { id: 'spam', label: 'Spam' }, { id: 'trash', label: 'Śmieci' }]
const stats = computed(() => report.value?.stats || {})
const messages = computed(() => report.value?.messages || [])
const received = computed(() => messages.value.filter(item => item.direction === 'received'))
const actionable = computed(() => received.value.filter(item => !item.spam && ['urgent', 'reply', 'payment'].includes(item.label)))
const groups = computed(() => [
  { id: 'attention', name: 'Wymagają uwagi', items: actionable.value },
  { id: 'urgent', name: 'Pilne', items: received.value.filter(item => !item.spam && item.label === 'urgent') },
  { id: 'reply', name: 'Do odpowiedzi', items: received.value.filter(item => !item.spam && item.label === 'reply') },
  { id: 'payment', name: 'Do zapłaty', items: received.value.filter(item => !item.spam && item.label === 'payment') },
  { id: 'info', name: 'Informacje', items: received.value.filter(item => !item.spam && item.label === 'info') },
  { id: 'clients', name: 'Od firm / klientów', items: received.value.filter(item => !item.spam && item.company) },
  { id: 'unread', name: 'Nieprzeczytane', items: received.value.filter(item => item.unread) },
  { id: 'sent', name: 'Wysłane', items: messages.value.filter(item => item.direction === 'sent') },
  { id: 'all', name: 'Wszystkie', items: messages.value },
  ...Object.entries(categories).map(([key, value]) => ({ id: `category:${key}`, name: value.name, items: received.value.filter(item => item.category === key) }))
])
const currentGroup = computed(() => groups.value.find(item => item.id === activeGroup.value) || groups.value[0])
const filtered = computed(() => currentGroup.value.items.filter(item => !search.value.trim() || [item.subject, item.sender_name, item.sender_email, item.company?.name].some(value => (value || '').toLocaleLowerCase('pl').includes(search.value.trim().toLocaleLowerCase('pl')))))
const categoryRows = computed(() => Object.entries(categories).map(([id, item]) => ({ id, ...item, count: stats.value.categories?.[id] || 0 })).filter(item => item.count > 0).sort((a, b) => b.count - a.count))
const donut = computed(() => {
  const total = categoryRows.value.reduce((sum, item) => sum + item.count, 0)
  if (!total) return 'var(--border)'
  let cursor = 0
  return `conic-gradient(${categoryRows.value.map(item => { const start = cursor; cursor += item.count / total * 100; return `${item.color} ${start}% ${cursor}%` }).join(',')})`
})
const hours = computed(() => {
  const values = Array(24).fill(0)
  for (const item of received.value) {
    const date = new Date(item.created_at)
    if (!Number.isNaN(date.getTime())) values[Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Warsaw', hour: '2-digit', hourCycle: 'h23' }).format(date))]++
  }
  return values
})
const maxHour = computed(() => Math.max(1, ...hours.value))
const peak = computed(() => hours.value.some(Boolean) ? `${String(hours.value.indexOf(Math.max(...hours.value))).padStart(2, '0')}:00` : '—')
const readableDay = computed(() => day.value ? new Date(`${day.value}T12:00:00`).toLocaleDateString('pl-PL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) : 'Wybierz dzień')
const updated = computed(() => report.value?.generated_at ? new Date(report.value.generated_at).toLocaleTimeString('pl-PL', { timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit' }) : '')
const percent = count => stats.value.received ? Math.round(count / stats.value.received * 100) : 0
function chooseGroup(id) { activeGroup.value = id; messageSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
async function loadReport() {
  if (loading.value) return
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day.value)) { report.value = null; error.value = 'Wybierz prawidłowy dzień raportu.'; return }
  loading.value = true; error.value = ''; report.value = null
  emit('day-change', day.value)
  try { report.value = await props.api('/client-mail/day-report', 'POST', { day: day.value }) }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}
async function moveDay(offset) {
  if (loading.value || !/^\d{4}-\d{2}-\d{2}$/.test(day.value)) return
  const value = new Date(`${day.value}T12:00:00Z`)
  value.setUTCDate(value.getUTCDate() + offset)
  day.value = value.toISOString().slice(0, 10)
  await loadReport()
}
function openMessage(id) {
  const message = messages.value.find(item => item.id === id)
  if (message) emit('open-message', { id: message.id, folder: message.folder })
}
watch([activeGroup, search], () => { limit.value = 12 })
watch(() => props.request, () => loadReport())
onMounted(loadReport)
</script>

<template>
  <section class="mail-analysis" aria-label="Analiza AI poczty" :aria-busy="loading">
    <Teleport to="#workspace-title"><div class="analysis-workspace-title"><h1>Analiza AI</h1><small>Poczta · przegląd dnia</small></div></Teleport>
    <header class="analysis-heading"><div><p class="analysis-eyebrow"><Sparkles :size="15" /> TWOJA POCZTA W LICZBACH</p><h2>Twój dzień w poczcie</h2><p>Wszystko, co warto dziś zauważyć — w jednym miejscu.</p></div><button class="analysis-inbox" @click="emit('open-folder', 'inbox')"><Inbox :size="17" /> Otwórz pocztę <ArrowUpRight :size="16" /></button></header>
    <div class="analysis-datebar"><div class="analysis-date-controls"><button :disabled="loading" title="Poprzedni dzień" aria-label="Poprzedni dzień" @click="moveDay(-1)"><ChevronLeft :size="18" /></button><input v-model="day" type="date" aria-label="Dzień raportu" :disabled="loading" @change="loadReport" /><button :disabled="loading" title="Następny dzień" aria-label="Następny dzień" @click="moveDay(1)"><ChevronRight :size="18" /></button><span class="analysis-readable-date">{{ readableDay }}</span></div><div class="analysis-date-actions"><span class="analysis-local"><ShieldCheck :size="14" /> Raport lokalny</span><button :disabled="loading || !day" title="Odśwież podsumowanie dnia" @click="loadReport"><RefreshCw :size="16" :class="{ spinning: loading }" /><span>{{ loading ? 'Wczytywanie…' : 'Odśwież' }}</span></button></div></div>
    <p v-if="error" class="analysis-error" role="alert">{{ error }} <button :disabled="loading" @click="loadReport">Spróbuj ponownie</button></p>
    <div v-if="loading" class="analysis-loading" role="status"><RefreshCw class="spinning" :size="25" /><p>Przygotowujemy przegląd Twojej poczty…</p></div>
    <template v-if="report">
      <div v-if="!stats.total" class="analysis-empty" role="status"><Inbox :size="24" /><div><strong>Spokojny dzień w skrzynce</strong><p>Brak wiadomości z tego dnia. Wybierz inną datę, aby zobaczyć raport.</p></div></div>
      <div class="analysis-kpis">
        <button class="analysis-kpi blue" @click="chooseGroup('all')"><span class="kpi-top"><span>Wiadomości dnia</span><Inbox :size="19" /></span><strong>{{ stats.total }}</strong><small>{{ stats.received }} odebranych · {{ stats.sent }} wysłanych</small></button>
        <button class="analysis-kpi rose" @click="chooseGroup('attention')"><span class="kpi-top"><span>Wymagają uwagi</span><AlertCircle :size="19" /></span><strong>{{ actionable.length }}</strong><small>{{ stats.urgent }} pilnych · {{ stats.reply }} do odpowiedzi</small></button>
        <button class="analysis-kpi green" @click="chooseGroup('clients')"><span class="kpi-top"><span>Od firm / klientów</span><Building2 :size="19" /></span><strong>{{ stats.clients }}</strong><small>{{ percent(stats.clients) }}% odebranej korespondencji</small></button>
        <button class="analysis-kpi amber" @click="chooseGroup('category:spam')"><span class="kpi-top"><span>Oznaczony spam</span><ShieldAlert :size="19" /></span><strong>{{ stats.spam }}</strong><small>{{ percent(stats.spam) }}% odebranych wiadomości</small></button>
      </div>
      <div class="analysis-mini-metrics"><button @click="chooseGroup('unread')"><Mail :size="17" /><span>Nieprzeczytane</span><strong>{{ stats.unread }}</strong></button><button @click="chooseGroup('category:invoice')"><FileText :size="17" /><span>Faktury</span><strong>{{ stats.categories.invoice }}</strong></button><button @click="chooseGroup('payment')"><CreditCard :size="17" /><span>Do zapłaty</span><strong>{{ stats.payment }}</strong></button><button @click="chooseGroup('sent')"><Send :size="17" /><span>Wysłane</span><strong>{{ stats.sent }}</strong></button></div>
      <div class="analysis-main-grid">
        <section class="analysis-panel analysis-categories"><header><div><h3>Jak wygląda Twoja poczta?</h3><p>Podział odebranych wiadomości</p></div><span class="analysis-panel-count">{{ stats.received }} wiadomości</span></header><div class="analysis-category-content"><div class="analysis-donut" :style="{ background: donut }" role="img" :aria-label="`Podział ${stats.received} odebranych wiadomości według kategorii`"><div><strong>{{ stats.received }}</strong><span>odebranych</span></div></div><div class="analysis-legend"><button v-for="item in categoryRows" :key="item.id" :title="`Pokaż wiadomości: ${item.name}`" @click="chooseGroup(`category:${item.id}`)"><i :style="{ background: item.color }"></i><span>{{ item.name }}</span><strong>{{ item.count }}</strong><small>{{ percent(item.count) }}%</small></button><p v-if="!categoryRows.length" class="analysis-muted">Brak danych dla wybranego dnia.</p></div></div></section>
        <section class="analysis-panel analysis-priorities"><header><div><h3>Najpierw najważniejsze</h3><p>Sprawy wynikające z Twoich oznaczeń</p></div><span class="analysis-priority-icon"><Sparkles :size="19" /></span></header><div class="analysis-priority-list"><button class="urgent" @click="chooseGroup('urgent')"><span><AlertCircle :size="18" /> Pilne wiadomości</span><strong>{{ stats.urgent }}</strong><ChevronRight :size="16" /></button><button @click="chooseGroup('reply')"><span><Reply :size="18" /> Czekają na odpowiedź</span><strong>{{ stats.reply }}</strong><ChevronRight :size="16" /></button><button @click="chooseGroup('payment')"><span><CreditCard :size="18" /> Oznaczone do zapłaty</span><strong>{{ stats.payment }}</strong><ChevronRight :size="16" /></button></div><div class="analysis-guidance"><strong>{{ actionable.length ? 'Plan na ten dzień' : 'Brak oznaczonych spraw do działania' }}</strong><ul v-if="report.analysis?.recommendations.length"><li v-for="item in report.analysis.recommendations" :key="item">{{ item }}</li></ul><p v-else>Możesz przejrzeć pozostałą korespondencję lub wybrać inny dzień.</p></div></section>
        <section class="analysis-panel"><header><div><h3>Rytm Twojej skrzynki</h3><p>Odebrane wiadomości według godziny</p></div><span class="analysis-hour-caption"><Clock3 :size="14" /> Szczyt: {{ peak }}</span></header><div class="analysis-hour-chart" role="img" :aria-label="`Odebrane według godzin: ${hours.map((count, hour) => `${hour}:00 — ${count}`).join(', ')}`"><div v-for="(count, hour) in hours" :key="hour" class="analysis-hour-column" :title="`${String(hour).padStart(2, '0')}:00 — ${count} wiadomości`"><div class="analysis-hour-track"><span :style="{ height: count ? `${Math.max(4, count / maxHour * 100)}%` : '2px' }" :class="{ 'is-zero': !count }"></span></div><small>{{ [0, 6, 12, 18, 23].includes(hour) ? String(hour).padStart(2, '0') : '' }}</small></div></div><p class="analysis-chart-note">Godziny według czasu polskiego.</p></section>
        <section class="analysis-panel"><header><div><h3>Firmy w Twojej korespondencji</h3><p>Udział w odebranych wiadomościach</p></div><Building2 :size="20" /></header><div class="analysis-companies"><button v-for="company in report.companies" :key="company.id" @click="chooseGroup('clients')"><span><span>{{ company.name }}</span><strong>{{ company.count }}</strong></span><span class="analysis-company-track"><i :style="{ width: `${percent(company.count)}%` }"></i></span></button><p v-if="!report.companies.length" class="analysis-muted">Brak wiadomości od przypisanych firm. Powiąż adres lub domenę z firmą w podglądzie wiadomości.</p></div></section>
      </div>
      <section ref="messageSection" class="analysis-panel analysis-messages"><header><div><h3>Wiadomości z dnia</h3><p>Wybierz grupę i otwórz wiadomość, aby przejść do jej treści.</p></div><label class="analysis-search"><Search :size="16" /><input v-model="search" type="search" placeholder="Szukaj w raporcie…" aria-label="Szukaj wiadomości w raporcie" /></label></header><div class="analysis-message-controls"><select v-model="activeGroup" aria-label="Grupa wiadomości"><option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }} ({{ group.items.length }})</option></select><span>{{ filtered.length }} wiadomości · {{ currentGroup.name }}</span></div><MailDayMessages :messages="filtered.slice(0, limit)" :folders="folders" @open="openMessage" /><button v-if="filtered.length > limit" class="analysis-show-more" @click="limit += 12">Pokaż kolejne ({{ filtered.length - limit }})</button></section>
      <footer class="analysis-footer"><span><ShieldCheck :size="14" /> Podsumowanie obliczane lokalnie</span><span v-if="updated">Odświeżono o {{ updated }}</span><p>Raport obejmuje wszystkie foldery poza Roboczymi. Firmy mogą być klientami lub dostawcami. Kategorie i etykiety pochodzą z zapisanych oznaczeń; brak oznaczonego spamu nie wyklucza go w wiadomościach bez kategorii.</p></footer>
    </template>
  </section>
</template>

<style scoped>
.mail-analysis { --report-purple:var(--accent,#7560d9); color:var(--text); min-width:0; display:flex; flex-direction:column; gap:22px; padding:4px 4px 24px; }
.mail-analysis > * { flex-shrink:0; }
.analysis-workspace-title h1 { margin:0; font-size:24px; }.analysis-workspace-title small { color:var(--muted); font-size:11px; }
.analysis-heading { display:flex; justify-content:space-between; align-items:center; gap:20px; flex-wrap:wrap; }.analysis-eyebrow { display:flex; align-items:center; gap:7px; color:var(--report-purple); font-size:10px; font-weight:700; letter-spacing:1.4px; margin:0 0 12px; }.analysis-heading h2 { font-size:30px; line-height:1.25; letter-spacing:-1px; margin:0 0 10px; }.analysis-heading > div > p:last-child { font-size:12px; color:var(--secondary); margin:0; }.analysis-inbox { font-size:12px; background:var(--surface); padding:11px 14px; }
.analysis-datebar { display:flex; align-items:center; justify-content:space-between; gap:14px; flex-wrap:wrap; padding:12px 14px; border:1px solid var(--border); border-radius:13px; background:var(--surface); }.analysis-date-controls,.analysis-date-actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }.analysis-datebar button { padding:8px; font-size:11px; border:0; background:transparent; }.analysis-datebar input { width:auto; max-width:100%; padding:8px; font-size:12px; background:var(--surface-soft); }.analysis-readable-date { font-size:11px; color:var(--secondary); padding-left:8px; }.analysis-local { display:flex; align-items:center; gap:5px; color:var(--success); font-size:10px; background:var(--success-soft); padding:6px 8px; border-radius:6px; }
.analysis-kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; }.analysis-kpi { --kpi-color:#6588d7; --kpi-tint:#6588d7; display:grid; justify-content:stretch; text-align:left; gap:15px; min-width:0; padding:20px; background:linear-gradient(135deg,color-mix(in srgb,var(--kpi-tint) 7%,var(--surface)),var(--surface)); border-radius:16px; }.analysis-kpi.rose { --kpi-color:var(--theme-danger,#c94f70); --kpi-tint:#e17e91; }.analysis-kpi.green { --kpi-color:var(--success,#229b86); --kpi-tint:#229b86; }.analysis-kpi.amber { --kpi-color:var(--warning,#a47936); --kpi-tint:#e8ae55; }.kpi-top { display:flex; align-items:center; justify-content:space-between; gap:10px; font-size:12px; color:var(--secondary); }.kpi-top svg { color:var(--kpi-color); flex-shrink:0; }.analysis-kpi > strong { font-size:35px; line-height:1; letter-spacing:-1px; }.analysis-kpi small { color:var(--secondary); font-size:10px; line-height:1.6; }
.analysis-mini-metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1px; background:var(--border); border:1px solid var(--border); border-radius:12px; overflow:hidden; }.analysis-mini-metrics button { justify-content:flex-start; gap:9px; border:0; border-radius:0; background:var(--surface); padding:14px; font-size:11px; min-width:0; }.analysis-mini-metrics svg { color:var(--muted); flex-shrink:0; }.analysis-mini-metrics strong { margin-left:auto; font-size:15px; }
.analysis-main-grid { display:grid; grid-template-columns:1.1fr 1fr; gap:20px; }.analysis-panel { min-width:0; padding:22px; background:var(--surface); border:1px solid var(--border); border-radius:16px; }.analysis-panel > header { display:flex; align-items:flex-start; justify-content:space-between; gap:15px; margin-bottom:22px; }.analysis-panel h3 { margin:0 0 7px; font-size:15px; letter-spacing:-.25px; }.analysis-panel header p { margin:0; font-size:11px; line-height:1.6; color:var(--secondary); }.analysis-panel-count { white-space:nowrap; padding:5px 8px; border-radius:6px; font-size:10px; color:var(--secondary); background:var(--surface-soft); }
.analysis-category-content { display:flex; gap:28px; align-items:center; }.analysis-donut { width:178px; height:178px; border-radius:50%; flex-shrink:0; padding:21px; transform:rotate(-90deg); }.analysis-donut > div { background:var(--surface); border-radius:50%; width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:5px; transform:rotate(90deg); }.analysis-donut strong { font-size:30px; letter-spacing:-1px; }.analysis-donut span { font-size:11px; color:var(--secondary); }.analysis-legend { flex:1; min-width:0; display:grid; gap:5px; }.analysis-legend button { display:flex; width:100%; gap:8px; padding:6px 0; border:0; background:transparent; font-size:11px; border-radius:5px; text-align:left; }.analysis-legend i { width:8px; height:8px; border-radius:50%; flex-shrink:0; }.analysis-legend button > span { flex:1; }.analysis-legend small { color:var(--muted); width:32px; text-align:right; font-size:10px; }
.analysis-priorities { background:linear-gradient(150deg,color-mix(in srgb,var(--report-purple) 5%,var(--surface)),var(--surface)); }.analysis-priority-icon { display:grid; place-items:center; padding:8px; color:var(--report-purple); background:var(--accent-soft); border-radius:10px; }.analysis-priority-list { display:grid; gap:8px; }.analysis-priority-list button { width:100%; justify-content:flex-start; background:var(--surface); font-size:12px; padding:12px; }.analysis-priority-list button > span { display:flex; align-items:center; gap:8px; flex:1; text-align:left; }.analysis-priority-list strong { padding:3px 7px; background:var(--surface-soft); border-radius:5px; }.analysis-priority-list .urgent { color:var(--theme-danger,#ba253b); }.analysis-guidance { margin-top:17px; font-size:11px; line-height:1.8; color:var(--secondary); }.analysis-guidance strong { color:var(--text); }.analysis-guidance ul { padding-left:17px; margin:7px 0 0; }.analysis-guidance p { margin-bottom:0; }
.analysis-hour-caption { display:flex; align-items:center; gap:5px; font-size:10px; color:var(--secondary); white-space:nowrap; }.analysis-hour-chart { display:flex; gap:5px; height:132px; padding-top:8px; }.analysis-hour-column { flex:1; min-width:0; display:flex; flex-direction:column; gap:9px; }.analysis-hour-track { height:105px; display:flex; align-items:flex-end; }.analysis-hour-track > span { width:100%; border-radius:4px 4px 1px 1px; background:#9283df; }.analysis-hour-track > span.is-zero { background:var(--border); }.analysis-hour-column small { font-size:9px; color:var(--muted); text-align:center; min-height:12px; }.analysis-chart-note { margin:14px 0 0; font-size:10px; color:var(--muted); }
.analysis-companies { display:grid; gap:17px; max-height:210px; overflow:auto; }.analysis-companies button { border:0; border-radius:0; background:transparent; padding:0; display:grid; justify-content:stretch; gap:8px; }.analysis-companies button > span:first-child { display:flex; justify-content:space-between; gap:15px; text-align:left; font-size:12px; }.analysis-company-track { height:6px; background:var(--surface-soft); overflow:hidden; border-radius:5px; }.analysis-company-track i { display:block; height:100%; border-radius:5px; background:#9a8be1; }.analysis-muted { font-size:12px; line-height:1.8; color:var(--secondary); margin:0; }
.analysis-messages { scroll-margin-top:20px; }.analysis-search { display:flex; align-items:center; gap:8px; flex-direction:row; padding:0 10px; border:1px solid var(--border); background:var(--surface-soft); border-radius:9px; color:var(--muted); min-width:0; }.analysis-search input { width:200px; max-width:100%; padding:9px 0; border:0; background:transparent; font-size:11px; }.analysis-message-controls { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; border-top:1px solid var(--border); padding-top:15px; }.analysis-message-controls select { width:240px; max-width:100%; font-size:12px; padding:10px; }.analysis-message-controls > span { color:var(--secondary); font-size:11px; }.analysis-show-more { margin-top:8px; font-size:12px; }
.analysis-footer { display:flex; gap:14px; flex-wrap:wrap; color:var(--muted); font-size:10px; line-height:1.8; }.analysis-footer > span { display:flex; align-items:center; gap:5px; }.analysis-footer p { width:100%; margin:0; }.analysis-error { color:var(--theme-danger,#ba253b); background:var(--danger-soft,var(--surface-soft)); padding:14px; border-radius:10px; font-size:12px; }.analysis-error button { margin-left:10px; padding:5px 8px; font-size:11px; }.analysis-loading { display:grid; place-items:center; min-height:300px; color:var(--secondary); font-size:13px; gap:10px; align-content:center; }.analysis-loading svg { color:var(--report-purple); }.analysis-empty { display:flex; gap:12px; align-items:center; padding:17px; border:1px solid var(--border); background:var(--surface); border-radius:12px; font-size:12px; }.analysis-empty svg { color:var(--report-purple); flex-shrink:0; }.analysis-empty p { margin:6px 0 0; color:var(--secondary); }
.spinning { animation:report-spin 1s linear infinite; }@keyframes report-spin { to { transform:rotate(360deg); } }@media(prefers-reduced-motion:reduce) { .spinning { animation:none; } }
@media(min-width:1251px) { .mail-analysis { flex:1; min-height:0; overflow-y:auto; padding-right:8px; } }
@media(max-width:1200px) { .analysis-kpis { gap:10px; }.analysis-kpi { padding:16px; }.analysis-category-content { gap:18px; }.analysis-donut { width:145px; height:145px; padding:17px; }.analysis-main-grid { grid-template-columns:1fr 1fr; gap:15px; }.analysis-panel { padding:18px; } }
@media(max-width:850px) { .analysis-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); }.analysis-main-grid { grid-template-columns:1fr; }.analysis-category-content { justify-content:center; }.analysis-donut { width:175px; height:175px; padding:21px; }.analysis-mini-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }.analysis-readable-date { display:none; } }
@media(max-width:520px) { .mail-analysis { gap:16px; }.analysis-heading h2 { font-size:25px; }.analysis-heading { align-items:flex-start; gap:14px; }.analysis-heading > div > p:last-child { font-size:11px; line-height:1.7; }.analysis-inbox { padding:9px 11px; font-size:11px; }.analysis-datebar { padding:9px; gap:9px; }.analysis-date-controls { gap:3px; }.analysis-datebar input { padding:6px; font-size:11px; }.analysis-date-actions { width:100%; justify-content:space-between; }.analysis-kpi { padding:14px 12px; gap:12px; }.kpi-top { font-size:11px; gap:6px; }.analysis-kpi > strong { font-size:30px; }.analysis-kpi small { font-size:9px; }.analysis-mini-metrics button { padding:12px 10px; font-size:10px; gap:7px; }.analysis-panel > header { flex-wrap:wrap; margin-bottom:17px; }.analysis-category-content { gap:18px; }.analysis-donut { width:130px; height:130px; padding:16px; }.analysis-donut strong { font-size:25px; }.analysis-legend button { font-size:10px; gap:5px; }.analysis-legend small { font-size:9px; width:27px; }.analysis-legend i { width:6px; height:6px; }.analysis-panel { padding:16px; }.analysis-panel-count { font-size:9px; }.analysis-search { width:100%; }.analysis-search input { width:100%; }.analysis-hour-chart { gap:3px; } }
</style>
