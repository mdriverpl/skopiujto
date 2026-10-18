<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { Mail, MailOpen, ArrowRight, RefreshCw, AlertCircle } from 'lucide-vue-next'

const props = defineProps({ api: Function, busy: Boolean, compact: Boolean })
const emit = defineEmits(['open'])
const stats = ref(null), loading = ref(false), error = ref('')
const ranges = [{ hours: 24, label: '24 h' }, { hours: 48, label: '48 h' }, { hours: 168, label: '7 dni' }, { hours: 720, label: '30 dni' }]
const hours = ref(24)
try {
  const saved = Number(localStorage.getItem('edokumenty-mail-range:inbox'))
  if (ranges.some(range => range.hours === saved)) hours.value = saved
} catch {}
const rangeLabel = computed(() => ranges.find(range => range.hours === hours.value).label)
const period = computed(() => Object.fromEntries(['total', 'unread', 'clients', 'government', 'other', 'invoices'].map(key =>
  [key, stats.value?.[key === 'total' ? 'period' : `period_${key}`] ?? stats.value?.[key === 'total' ? 'today' : `today_${key}`] ?? 0])))
function saveRange() { try { localStorage.setItem('edokumenty-mail-range:inbox', String(hours.value)) } catch {} }
async function selectRange(value) {
  if (loading.value || hours.value === value || !ranges.some(range => range.hours === value)) return
  hours.value = value; stats.value = null; saveRange()
  await refresh()
}
function openMailbox() { saveRange(); emit('open') }
const breakdown = [
  { key: 'clients', label: 'Od klientów', hint: 'Wiadomości w wybranym okresie od adresów lub domen przypisanych do firmy, w tym od dostawców.' },
  { key: 'government', label: 'Od urzędu', hint: 'Wiadomości w wybranym okresie z rozpoznanych domen rządowych. Domena nie potwierdza autentyczności wiadomości.' },
  { key: 'other', label: 'Inne', hint: 'Pozostali nadawcy w wybranym okresie, bez przypisanej firmy i oznaczenia domeny rządowej.' },
  { key: 'invoices', label: 'Faktury', hint: 'Wiadomości w wybranym okresie z etykietą lub kategorią Faktura. Mogą również być liczone jako wiadomości od klientów, urzędu lub innych nadawców.' }
]
let timer, disposed = false
async function refresh() {
  if (loading.value || disposed) return
  loading.value = true; error.value = ''
  try {
    const result = await props.api(`/client-mail/summary?hours=${hours.value}`)
    if (!disposed) stats.value = result
  } catch {
    if (!disposed) error.value = 'Nie udało się odświeżyć liczby wiadomości.'
  } finally { if (!disposed) loading.value = false }
}
function refreshVisible() { if (document.visibilityState === 'visible') refresh() }
onMounted(() => {
  refresh()
  timer = setInterval(refreshVisible, 60000)
  document.addEventListener('visibilitychange', refreshVisible)
  window.addEventListener('focus', refreshVisible)
})
onBeforeUnmount(() => {
  disposed = true; clearInterval(timer)
  document.removeEventListener('visibilitychange', refreshVisible)
  window.removeEventListener('focus', refreshVisible)
})
</script>

<template>
  <section v-if="compact" class="compact-mail-card">
    <div class="mail-card-ranges" role="group" aria-label="Okres statystyk wiadomości"><button v-for="range in ranges" :key="range.hours" type="button" :aria-pressed="hours === range.hours" :disabled="loading" @click="selectRange(range.hours)">{{ range.label }}</button></div>
    <button class="compact-mail-open" :disabled="busy" aria-label="Otwórz wiadomości — wiadomości odebrane" @click="openMailbox"><span class="compact-mail-icon"><Mail :size="27" /><span v-if="stats" class="compact-mail-badge">{{ period.total > 99 ? '99+' : period.total }}</span></span><strong>Centrum wiadomości</strong><small>{{ stats ? rangeLabel + ': ' + period.total : loading ? 'Sprawdzanie poczty…' : 'Licznik niedostępny' }}</small><span v-if="stats" class="mail-breakdown compact-breakdown" aria-label="Poczta w wybranym okresie według nadawcy i faktury"><span v-for="item in breakdown" :key="item.key" :title="item.hint">{{ item.label }}: <b>{{ period[item.key] }}</b></span></span></button>
    <button class="compact-mail-refresh" :disabled="loading" title="Odśwież liczbę wiadomości" aria-label="Odśwież liczbę wiadomości" @click="refresh"><RefreshCw :size="14" :class="{ spinning: loading }" /></button><span v-if="error" class="compact-mail-error" role="status">Nie udało się odświeżyć licznika</span>
  </section>
  <section v-else class="start-mail panel" aria-labelledby="start-mail-title">
    <header><h2 id="start-mail-title"><Mail :size="18" /> Centrum wiadomości</h2><div class="mail-card-ranges" role="group" aria-label="Okres statystyk wiadomości"><button v-for="range in ranges" :key="range.hours" type="button" :aria-pressed="hours === range.hours" :disabled="loading" @click="selectRange(range.hours)">{{ range.label }}</button></div><button class="icon-button" :disabled="loading" title="Odśwież liczbę nowych wiadomości" aria-label="Odśwież liczbę nowych wiadomości" @click="refresh"><RefreshCw :size="17" :class="{ spinning: loading }" /></button></header>
    <button class="start-mail-open" :disabled="busy" aria-label="Otwórz wiadomości — wiadomości odebrane" @click="openMailbox">
      <span class="start-mail-art" aria-hidden="true"><span class="mail-art-orbit"></span><span class="mail-art-envelope"><Mail v-if="!stats || period.total" :size="62" :stroke-width="1.4" /><MailOpen v-else :size="62" :stroke-width="1.4" /></span><span v-if="period.total" class="mail-art-badge">{{ period.total > 99 ? '99+' : period.total }}</span><span class="mail-art-dot"></span></span>
      <span class="start-mail-content"><span class="mail-card-eyebrow">Twoja korespondencja</span><span class="start-mail-count" aria-live="polite"><strong>{{ stats ? period.total : '—' }}</strong><span>Wiadomości · {{ rangeLabel }}<small>Nieprzeczytane: {{ period.unread }}</small></span></span><span v-if="stats" class="start-mail-meta"><span>Odebrane łącznie <b>{{ stats.total }}</b></span><span>Nieprzeczytane łącznie <b>{{ stats.unread }}</b></span><span v-if="stats.urgent" class="start-mail-urgent"><AlertCircle :size="14" /> Pilne <b>{{ stats.urgent }}</b></span><span v-else-if="!stats.unread" class="start-mail-clear">Wszystkie wiadomości przeczytane</span></span><span v-else class="start-mail-meta">{{ loading ? 'Sprawdzanie poczty…' : 'Otwórz swoją skrzynkę' }}</span><span v-if="stats" class="mail-breakdown" aria-label="Poczta w wybranym okresie według nadawcy i faktury"><span v-for="item in breakdown" :key="item.key" :title="item.hint">{{ item.label }}: <b>{{ period[item.key] }}</b></span></span></span>
      <span class="start-mail-link">Otwórz wiadomości <ArrowRight :size="18" /></span>
    </button>
    <p v-if="error" class="start-mail-error" role="status">{{ error }} Użyj ikony odświeżania, aby spróbować ponownie.</p>
  </section>
</template>

<style scoped>
.mail-card-ranges { display:inline-flex; align-items:center; gap:3px; padding:4px; border:1px solid color-mix(in srgb,var(--accent) 10%,var(--border)); border-radius:12px; background:color-mix(in srgb,var(--surface) 75%,transparent); }
.mail-card-ranges button { padding:7px 11px; border:0; border-radius:8px; color:var(--muted); background:transparent; font-size:11px; white-space:nowrap; transition:background .15s,color .15s,box-shadow .15s; }
.mail-card-ranges button[aria-pressed="true"] { color:var(--accent); background:var(--surface); box-shadow:0 2px 8px #34256d12; font-weight:600; }
header .mail-card-ranges { margin-left:auto; margin-right:10px; }.compact-mail-card > .mail-card-ranges { margin:38px 12px 0; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:2px; }.compact-mail-card > .mail-card-ranges button { min-width:0; padding:6px 2px; font-size:9px; }
.compact-mail-card.orbit-mail { display:flex; flex-direction:column; aspect-ratio:auto; min-height:250px; }.compact-mail-card .compact-mail-open { height:auto; flex:1; padding:14px 18px 18px; gap:8px; }.compact-mail-card .compact-mail-icon { width:40px; height:40px; flex-shrink:0; }.compact-mail-card .compact-breakdown { grid-template-columns:1fr; gap:4px; }
@media(max-width:600px) { header { flex-wrap:wrap; gap:10px; }header .mail-card-ranges { order:3; width:100%; margin:0; }header .mail-card-ranges button { flex:1; }header > button { margin-left:auto; } }
.compact-mail-card { position:relative; }.compact-mail-open { display:flex; flex-direction:column; justify-content:center; align-items:flex-start; gap:9px; width:100%; height:100%; padding:20px 24px; border:0; border-radius:inherit; background:transparent; text-align:left; }.compact-mail-icon { position:relative; display:grid; place-items:center; width:48px; height:48px; border-radius:15px; background:var(--accent-soft); color:var(--accent); }.compact-mail-badge { position:absolute; top:-7px; right:-10px; display:grid; place-items:center; min-width:24px; height:24px; padding:0 5px; border-radius:20px; color:white; background:var(--theme-danger,#ed4764); border:2px solid var(--surface); font-size:10px; font-weight:700; }.compact-mail-open > strong { font-size:15px; }.compact-mail-open > small { font-size:11px; color:var(--secondary); line-height:1.5; }.compact-breakdown { width:100%; font-size:10px; gap:5px 8px; }.compact-mail-refresh { position:absolute; right:10px; top:10px; padding:6px; border:0; background:transparent; color:var(--muted); }.compact-mail-error { display:block; padding:0 20px 10px; font-size:10px; color:var(--theme-danger,#ba253b); }
.start-mail { position:relative; overflow:hidden; margin-bottom:28px; border-radius:22px; background:linear-gradient(115deg,var(--accent-soft),var(--surface) 60%); }
header { display:flex; align-items:center; justify-content:space-between; padding:14px 22px 0; }h2 { display:flex; align-items:center; gap:9px; font-size:14px; margin:0; }h2 svg { color:var(--accent); }header button { background:transparent; padding:7px; }
.start-mail-open { display:grid; grid-template-columns:155px minmax(0,1fr) auto; align-items:center; gap:25px; width:100%; padding:6px 30px 25px; text-align:left; border:0; border-radius:0; background:transparent; }.start-mail-open:hover { background:color-mix(in srgb,var(--accent-soft) 35%,transparent); }
.start-mail-art { position:relative; display:grid; place-items:center; width:150px; height:140px; }.mail-art-orbit { position:absolute; width:132px; height:132px; border:1px dashed color-mix(in srgb,var(--accent) 30%,var(--border)); border-radius:50%; transform:rotate(-20deg); }.mail-art-envelope { display:grid; place-items:center; width:104px; height:88px; border-radius:23px; color:var(--theme-on-accent,white); background:linear-gradient(135deg,var(--accent),color-mix(in srgb,var(--accent) 65%,#58b4ff)); transform:rotate(-9deg); box-shadow:0 14px 28px color-mix(in srgb,var(--accent) 22%,transparent); }.mail-art-badge { position:absolute; top:13px; right:7px; min-width:30px; height:30px; padding:0 7px; display:grid; place-items:center; border:3px solid var(--surface); border-radius:20px; background:var(--theme-danger,#ed4764); color:white; font-size:11px; font-weight:700; }.mail-art-dot { position:absolute; width:9px; height:9px; border-radius:50%; background:var(--accent); left:4px; bottom:26px; }
.start-mail-content { display:grid; gap:10px; min-width:0; }.mail-card-eyebrow { color:var(--secondary); font-size:11px; }.start-mail-count { display:flex; align-items:center; gap:17px; }.start-mail-count > strong { font-size:46px; line-height:1; letter-spacing:-2px; color:var(--accent); }.start-mail-count > span { font-size:16px; font-weight:600; }.start-mail-count small { display:block; color:var(--secondary); font-size:11px; font-weight:400; margin-top:6px; }.start-mail-meta { display:flex; flex-wrap:wrap; align-items:center; gap:10px 18px; color:var(--secondary); font-size:11px; }.start-mail-meta > span { display:inline-flex; align-items:center; gap:6px; }.start-mail-meta b { color:var(--text); }.start-mail-meta .start-mail-urgent { color:var(--theme-danger,#ba253b); }.start-mail-meta .start-mail-clear { color:var(--success); }
.mail-breakdown { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px 16px; color:var(--secondary); font-size:11px; }.mail-breakdown b { color:var(--text); }.start-mail-link { display:inline-flex; align-items:center; justify-content:center; gap:12px; padding:12px 16px; border-radius:11px; color:var(--accent); background:var(--accent-soft); font-size:12px; font-weight:600; }.start-mail-error { margin:0; padding:0 22px 16px; font-size:11px; line-height:1.6; color:var(--theme-danger,#ba253b); }.spinning { animation:mail-refresh 1s linear infinite; }@keyframes mail-refresh { to { transform:rotate(360deg); } }
@media(max-width:850px) { .start-mail-open { grid-template-columns:120px minmax(0,1fr); gap:12px 20px; padding:8px 22px 24px; }.start-mail-art { width:120px; height:130px; }.mail-art-orbit { width:118px; height:118px; }.start-mail-link { grid-column:2; justify-self:start; } }
@media(max-width:480px) { header { padding:12px 16px 0; }.start-mail-open { grid-template-columns:86px minmax(0,1fr); gap:12px; padding:10px 16px 20px; }.start-mail-art { width:86px; height:100px; }.mail-art-orbit { width:85px; height:85px; }.mail-art-envelope { width:72px; height:65px; border-radius:17px; }.mail-art-envelope svg { width:46px; }.mail-art-badge { right:-3px; top:0; }.start-mail-count { gap:10px; }.start-mail-count > strong { font-size:36px; }.start-mail-count > span { font-size:13px; }.start-mail-count small { line-height:1.5; }.start-mail-link { grid-column:1 / -1; justify-self:stretch; }.mail-art-dot { width:6px; height:6px; left:0; bottom:12px; } }
@media(prefers-reduced-motion:reduce) { .spinning { animation:none; } }
</style>
