<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { ListTodo, CalendarDays, ArrowRight, AlertCircle } from 'lucide-vue-next'
import { startWorkSummary } from './startWorkSummary.js'

const props = defineProps({ tasks: Array, busy: Boolean })
const emit = defineEmits(['navigate'])
const clock = ref(new Date())
let timer
onMounted(() => { timer = setInterval(() => { clock.value = new Date() }, 60000) })
onBeforeUnmount(() => clearInterval(timer))
const stats = computed(() => startWorkSummary(props.tasks, clock.value))
const panels = computed(() => [
  { id: 'tasks', title: 'Zadania', count: stats.value.tasks, heading: 'Do wykonania łącznie',
    description: 'Twoje niezakończone zadania', action: 'Otwórz zadania',
    details: [['Do rozpoczęcia', stats.value.todo], ['W toku', stats.value.inProgress],
      ['Oczekujące', stats.value.waiting], ['Po terminie', stats.value.overdue]],
    note: 'Po terminie obejmuje niezakończone zadania z datą i godziną wcześniejszą niż teraz.' },
  { id: 'calendar', title: 'Terminarz', count: stats.value.dueToday, heading: 'Terminy dzisiaj',
    description: 'Niezakończone zadania według terminu', action: 'Otwórz terminarz',
    details: [['Jutro', stats.value.tomorrow], ['Najbliższe 7 dni', stats.value.week],
      ['Po terminie', stats.value.overdue], ['Bez terminu', stats.value.undated]],
    note: 'Dzisiaj według czasu polskiego. Najbliższe 7 dni obejmuje dzisiaj i sześć kolejnych dni. Bez terminu: zadania poza kalendarzem.' }
])
</script>

<template>
  <div class="start-work-panels">
    <section v-for="panel in panels" :key="panel.id" class="panel start-work" :class="panel.id" :aria-label="panel.title">
      <header><h2><ListTodo v-if="panel.id === 'tasks'" :size="18" /><CalendarDays v-else :size="18" />{{ panel.title }}</h2></header>
      <button class="work-open" :disabled="busy" @click="emit('navigate', panel.id)">
        <span class="work-art" aria-hidden="true"><span class="work-orbit"></span><span class="work-symbol"><ListTodo v-if="panel.id === 'tasks'" :size="62" :stroke-width="1.4" /><CalendarDays v-else :size="62" :stroke-width="1.4" /></span><span class="work-badge">{{ panel.count > 99 ? '99+' : panel.count }}</span><span class="work-dot"></span></span>
        <span class="work-content"><small>{{ panel.description }}</small><span class="work-count"><strong>{{ panel.count }}</strong><span>{{ panel.heading }}<small v-if="stats.overdue" class="work-overdue"><AlertCircle :size="12" /> Po terminie: {{ stats.overdue }}</small><small v-else>Brak zaległych zadań</small></span></span><span class="work-details" :title="panel.note"><span v-for="[label, count] in panel.details" :key="label">{{ label }}: <b>{{ count }}</b></span></span></span>
        <span class="work-link">{{ panel.action }} <ArrowRight :size="18" /></span>
      </button>
    </section>
  </div>
</template>

<style scoped>
.start-work-panels { display:grid; grid-template-columns:minmax(0,1fr); gap:20px; margin-bottom:28px; }
.start-work { --work-color:#bc7b17; --work-soft:color-mix(in srgb,#e3a32f 12%,var(--surface)); overflow:hidden; border-radius:22px; background:linear-gradient(115deg,var(--work-soft),var(--surface) 60%); }
.start-work.calendar { --work-color:#2879dd; --work-soft:color-mix(in srgb,#4899ed 12%,var(--surface)); }
header { padding:18px 22px 0; }h2 { display:flex; align-items:center; gap:9px; font-size:14px; margin:0; }h2 svg { color:var(--work-color); }
.work-open { display:grid; grid-template-columns:155px minmax(0,1fr) auto; align-items:center; gap:25px; width:100%; padding:10px 30px 25px; border:0; border-radius:0; text-align:left; background:transparent; }.work-open:hover { background:color-mix(in srgb,var(--work-soft) 35%,transparent); }
.work-art { position:relative; display:grid; place-items:center; width:150px; height:140px; }.work-orbit { position:absolute; width:132px; height:132px; border:1px dashed color-mix(in srgb,var(--work-color) 35%,var(--border)); border-radius:50%; }.work-symbol { display:grid; place-items:center; width:104px; height:88px; border-radius:23px; color:white; background:linear-gradient(135deg,var(--work-color),color-mix(in srgb,var(--work-color) 65%,#67c9d9)); transform:rotate(-9deg); box-shadow:0 14px 28px color-mix(in srgb,var(--work-color) 20%,transparent); }.calendar .work-symbol { transform:rotate(7deg); }.work-badge { position:absolute; top:13px; right:7px; min-width:30px; height:30px; padding:0 7px; display:grid; place-items:center; border:3px solid var(--surface); border-radius:20px; background:var(--work-color); color:white; font-size:11px; font-weight:700; }.work-dot { position:absolute; width:9px; height:9px; border-radius:50%; background:var(--work-color); left:4px; bottom:26px; }
.work-content { display:grid; gap:12px; min-width:0; }.work-content > small { color:var(--secondary); font-size:11px; }.work-count { display:flex; align-items:center; gap:17px; }.work-count > strong { color:var(--work-color); font-size:46px; line-height:1; letter-spacing:-2px; }.work-count > span { font-size:16px; font-weight:600; }.work-count small { display:flex; align-items:center; gap:5px; font-size:11px; font-weight:400; color:var(--secondary); margin-top:6px; }.work-count .work-overdue { color:var(--theme-danger,#ba253b); }.work-details { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px 16px; color:var(--secondary); font-size:11px; }.work-details b { color:var(--text); }
.work-link { display:inline-flex; align-items:center; justify-content:center; gap:12px; padding:12px 16px; border-radius:11px; color:var(--work-color); background:var(--work-soft); font-size:12px; font-weight:600; }
@media(max-width:850px) { .work-open { grid-template-columns:120px minmax(0,1fr); gap:12px 20px; padding:8px 22px 24px; }.work-art { width:120px; height:130px; }.work-orbit { width:118px; height:118px; }.work-link { grid-column:2; justify-self:start; } }
@media(max-width:480px) { header { padding:16px 16px 0; }.work-open { grid-template-columns:86px minmax(0,1fr); gap:12px; padding:10px 16px 20px; }.work-art { width:86px; height:100px; }.work-orbit { width:85px; height:85px; }.work-symbol { width:72px; height:65px; border-radius:17px; }.work-symbol svg { width:46px; }.work-badge { right:-3px; top:0; }.work-count { gap:10px; }.work-count > strong { font-size:36px; }.work-count > span { font-size:13px; }.work-details { grid-template-columns:1fr; }.work-link { grid-column:1 / -1; justify-self:stretch; }.work-dot { width:6px; height:6px; left:0; bottom:12px; } }
</style>
