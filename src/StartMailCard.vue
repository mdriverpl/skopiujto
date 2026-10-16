<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { Mail, MailOpen, ArrowRight, RefreshCw, AlertCircle } from 'lucide-vue-next'

const props = defineProps({ api: Function, busy: Boolean, compact: Boolean })
const emit = defineEmits(['open'])
const stats = ref(null), loading = ref(false), error = ref('')
const breakdown = [
  { key: 'today_clients', label: 'Od klientów', hint: 'Dzisiejsze wiadomości od adresów lub domen przypisanych do firmy, w tym od dostawców.' },
  { key: 'today_government', label: 'Od urzędu', hint: 'Dzisiejsze wiadomości z rozpoznanych domen rządowych. Domena nie potwierdza autentyczności wiadomości.' },
  { key: 'today_other', label: 'Inne', hint: 'Pozostali dzisiejsi nadawcy, bez przypisanej firmy i oznaczenia domeny rządowej.' },
  { key: 'today_invoices', label: 'Faktury', hint: 'Dzisiejsze wiadomości z etykietą lub kategorią Faktura. Mogą również być liczone jako wiadomości od klientów, urzędu lub innych nadawców.' }
]
let timer, disposed = false
async function refresh() {
  if (loading.value || disposed) return
  loading.value = true; error.value = ''
  try {
    const result = await props.api('/client-mail/summary')
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
    <button class="compact-mail-open" :disabled="busy" aria-label="Otwórz pocztę — wiadomości odebrane" @click="emit('open')"><span class="compact-mail-icon"><Mail :size="27" /><span v-if="stats" class="compact-mail-badge">{{ stats.today > 99 ? '99+' : stats.today }}</span></span><strong>Poczta</strong><small>{{ stats ? 'Dzisiaj: ' + stats.today : loading ? 'Sprawdzanie poczty…' : 'Licznik niedostępny' }}</small><span v-if="stats" class="mail-breakdown compact-breakdown" aria-label="Dzisiejsza poczta według nadawcy i faktury"><span v-for="item in breakdown" :key="item.key" :title="item.hint">{{ item.label }}: <b>{{ stats[item.key] ?? 0 }}</b></span></span></button>
    <button class="compact-mail-refresh" :disabled="loading" title="Odśwież liczbę wiadomości" aria-label="Odśwież liczbę wiadomości" @click="refresh"><RefreshCw :size="14" :class="{ spinning: loading }" /></button><span v-if="error" class="compact-mail-error" role="status">Nie udało się odświeżyć licznika</span>
  </section>
  <section v-else class="start-mail panel" aria-labelledby="start-mail-title">
    <header><h2 id="start-mail-title"><Mail :size="18" /> Poczta</h2><button class="icon-button" :disabled="loading" title="Odśwież liczbę nowych wiadomości" aria-label="Odśwież liczbę nowych wiadomości" @click="refresh"><RefreshCw :size="17" :class="{ spinning: loading }" /></button></header>
    <button class="start-mail-open" :disabled="busy" aria-label="Otwórz pocztę — wiadomości odebrane" @click="emit('open')">
      <span class="start-mail-art" aria-hidden="true"><span class="mail-art-orbit"></span><span class="mail-art-envelope"><Mail v-if="!stats || stats.today" :size="62" :stroke-width="1.4" /><MailOpen v-else :size="62" :stroke-width="1.4" /></span><span v-if="stats?.today" class="mail-art-badge">{{ stats.today > 99 ? '99+' : stats.today }}</span><span class="mail-art-dot"></span></span>
      <span class="start-mail-content"><span class="mail-card-eyebrow">Twoja korespondencja</span><span class="start-mail-count" aria-live="polite"><strong>{{ stats ? stats.today : '—' }}</strong><span>Wiadomości dzisiaj<small>Nieprzeczytane dzisiaj: {{ stats?.today_unread ?? 0 }}</small></span></span><span v-if="stats" class="start-mail-meta"><span>Odebrane łącznie <b>{{ stats.total }}</b></span><span>Nieprzeczytane łącznie <b>{{ stats.unread }}</b></span><span v-if="stats.urgent" class="start-mail-urgent"><AlertCircle :size="14" /> Pilne <b>{{ stats.urgent }}</b></span><span v-else-if="!stats.unread" class="start-mail-clear">Wszystkie wiadomości przeczytane</span></span><span v-else class="start-mail-meta">{{ loading ? 'Sprawdzanie poczty…' : 'Otwórz swoją skrzynkę' }}</span><span v-if="stats" class="mail-breakdown" aria-label="Dzisiejsza poczta według nadawcy i faktury"><span v-for="item in breakdown" :key="item.key" :title="item.hint">{{ item.label }}: <b>{{ stats[item.key] ?? 0 }}</b></span></span></span>
      <span class="start-mail-link">Otwórz pocztę <ArrowRight :size="18" /></span>
    </button>
    <p v-if="error" class="start-mail-error" role="status">{{ error }} Użyj ikony odświeżania, aby spróbować ponownie.</p>
  </section>
</template>

<style scoped>
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
