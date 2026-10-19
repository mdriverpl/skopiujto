<script setup>
import { computed } from 'vue'
import { ListTodo, CalendarDays, HardDrive, FileText, ClipboardCheck, StickyNote, Sparkles, ArrowUpRight, Mic, ArrowRight } from 'lucide-vue-next'
import StartMailCard from './StartMailCard.vue'
import EdzioAvatar from './EdzioAvatar.vue'
const props = defineProps({ api: Function, busy: Boolean, summary: Object, greeting: Object })
const emit = defineEmits(['navigate', 'command', 'dictate', 'analysis'])
const tiles = computed(() => [
  { id: 'tasks', name: 'Zadania', hint: 'Czekają na wykonanie', icon: ListTodo, count: props.summary.tasks.length, color: 'amber' },
  { id: 'calendar', name: 'Terminarz', hint: 'Zadania z terminem', icon: CalendarDays, count: props.summary.tasks.filter(item => item.due_at).length, color: 'blue' },
  { id: 'drive', name: 'Mój dysk', hint: 'Twoje pliki i katalogi', icon: HardDrive, color: 'teal' },
  { id: 'documents', name: 'Dokumenty', hint: 'Dokumenty i podgląd PDF', icon: FileText, color: 'blue' },
  { id: 'surveys', name: 'Ankiety', hint: 'Czekają na odpowiedź', icon: ClipboardCheck, count: props.summary.surveys.length, color: 'rose' },
  { id: 'notes', name: 'Notatki', hint: 'Pomysły i ustalenia', icon: StickyNote, color: 'amber' },
  { id: 'analysis', name: 'Analiza AI', hint: 'Podsumowanie Twojej poczty', icon: Sparkles, color: 'violet' }
])
</script>

<template>
  <section class="start-orbit" aria-label="Start — centrum Edzia">
    <div class="orbit-intro"><span class="orbit-kicker"><span></span> Wszystko w jednym miejscu</span><h1>Twój dzień. Pod kontrolą.</h1><p>Wybierz sprawę albo poproś Edzia o pomoc.</p></div>
    <div class="orbit-board">
      <svg class="orbit-connections" viewBox="0 0 1000 650" preserveAspectRatio="none" aria-hidden="true"><g><path d="M500 325L160 80M500 325V80M500 325L840 80M500 325H160M500 325H840M500 325L160 570M500 325V570M500 325L840 570"/><ellipse cx="500" cy="325" rx="280" ry="225"/><ellipse cx="500" cy="325" rx="180" ry="145"/></g></svg>
      <StartMailCard class="orbit-node orbit-mail" compact :api="api" :busy="busy" @open="emit('navigate', 'mail')" />
      <div class="orbit-center"><span class="edzio-halo halo-one"></span><span class="edzio-halo halo-two"></span><button class="orbit-edzio" :disabled="busy" title="Porozmawiaj z Edziem" aria-label="Porozmawiaj z Edziem, asystentem AI" @click="emit('command')"><EdzioAvatar /><strong>Edzio<span></span></strong><small>Twój asystent AI</small></button><button class="orbit-mic" :disabled="busy" title="Powiedz Edziowi, co ma zrobić" aria-label="Dyktuj polecenie Edziowi" @click="emit('dictate')"><Mic :size="20" /></button><span class="edzio-caption">Jestem tutaj, żeby pomóc <Sparkles :size="13" /></span></div>
      <button v-for="tile in tiles" :key="tile.id" class="orbit-node orbit-tile" :class="['orbit-' + tile.id, 'orbit-color-' + tile.color]" :disabled="busy" :aria-label="tile.name + (tile.count !== undefined ? ': ' + tile.count : '')" @click="tile.id === 'analysis' ? emit('analysis') : emit('navigate', tile.id)"><ArrowUpRight class="orbit-tile-arrow" :size="17" /><span class="orbit-icon"><component :is="tile.icon" :size="27" /><span v-if="tile.count !== undefined" class="orbit-badge">{{ tile.count > 99 ? '99+' : tile.count }}</span></span><strong>{{ tile.name }}</strong><small>{{ tile.hint }}</small></button>
    </div>
    <div class="orbit-greeting"><span class="greeting-spark"><Sparkles :size="20" /></span><div><strong>{{ greeting.title }}</strong><p>{{ greeting.description }}</p></div><button :disabled="busy" @click="emit('command')">Porozmawiajmy <ArrowRight :size="16" /></button></div>
  </section>
</template>

<style scoped>
.start-orbit { position:relative; isolation:isolate; padding:20px 25px 24px; border:1px solid var(--border); border-radius:28px; background:radial-gradient(ellipse at 50% 45%,var(--accent-soft),transparent 66%),var(--surface-soft); overflow:hidden; }.orbit-intro { text-align:center; margin-bottom:20px; }.orbit-kicker { display:inline-flex; align-items:center; gap:7px; color:var(--secondary); font-size:10px; }.orbit-kicker > span { width:6px; height:6px; border-radius:50%; background:var(--success); }.orbit-intro h1 { font-size:clamp(24px,2.6vw,34px); letter-spacing:-1.1px; margin:10px 0 8px; }.orbit-intro p { font-size:12px; color:var(--secondary); margin:0; }
.orbit-board { position:relative; max-width:820px; margin:0 auto; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); grid-template-rows:auto minmax(240px,auto) auto; gap:22px 44px; align-items:center; justify-items:center; padding:8px 0 20px; }.orbit-connections { position:absolute; inset:0; width:100%; height:100%; z-index:-1; overflow:visible; }.orbit-connections g { stroke:var(--accent); stroke-opacity:.17; stroke-width:1; fill:none; stroke-dasharray:5 8; }.orbit-connections ellipse { stroke-opacity:.12; }
.orbit-node { position:relative; min-width:0; height:auto; width:100%; max-width:220px; aspect-ratio:1; border:1px solid var(--border); border-radius:50px; background:color-mix(in srgb,var(--surface) 94%,transparent); box-shadow:0 7px 24px color-mix(in srgb,var(--accent) 5%,transparent); transition:transform .2s,border-color .2s,box-shadow .2s; }.orbit-node:hover { transform:translateY(-4px); border-color:color-mix(in srgb,var(--accent) 50%,var(--border)); box-shadow:0 12px 25px color-mix(in srgb,var(--accent) 12%,transparent); }.orbit-tile { display:flex; align-items:flex-start; justify-content:center; flex-direction:column; gap:9px; padding:20px 24px; text-align:left; }.orbit-tile > strong { font-size:15px; }.orbit-tile > small { font-size:11px; line-height:1.5; color:var(--secondary); }.orbit-tile-arrow { position:absolute; top:17px; right:17px; color:var(--muted); opacity:.7; }.orbit-icon { position:relative; display:grid; place-items:center; width:48px; height:48px; border-radius:15px; background:var(--orbit-soft,var(--accent-soft)); color:var(--orbit-color,var(--accent)); }.orbit-badge { position:absolute; top:-7px; right:-10px; min-width:24px; height:24px; padding:0 5px; display:grid; place-items:center; border-radius:20px; background:var(--orbit-color,var(--accent)); color:white; border:2px solid var(--surface); font-size:10px; font-weight:700; }.orbit-color-amber { --orbit-color:#bd7b12; --orbit-soft:color-mix(in srgb,#e3a32f 13%,var(--surface)); }.orbit-color-blue { --orbit-color:#2879dd; --orbit-soft:color-mix(in srgb,#4899ed 13%,var(--surface)); }.orbit-color-teal { --orbit-color:#138f86; --orbit-soft:color-mix(in srgb,#23aca0 13%,var(--surface)); }.orbit-color-rose { --orbit-color:#ce5176; --orbit-soft:color-mix(in srgb,#e87598 13%,var(--surface)); }
.orbit-mail { grid-area:1 / 1; }.orbit-tasks { grid-area:1 / 2; }.orbit-calendar { grid-area:1 / 3; }.orbit-drive { grid-area:2 / 1; }.orbit-documents { grid-area:2 / 3; }.orbit-surveys { grid-area:3 / 1; }.orbit-notes { grid-area:3 / 2; }.orbit-analysis { grid-area:3 / 3; }
.orbit-center { grid-area:2 / 2; position:relative; display:flex; align-items:center; justify-content:center; height:240px; flex-direction:column; }.edzio-halo { position:absolute; width:220px; height:220px; border-radius:50%; border:1px solid color-mix(in srgb,var(--accent) 20%,transparent); pointer-events:none; }.halo-two { width:270px; height:270px; border-style:dashed; opacity:.65; }.orbit-edzio { position:relative; display:flex; flex-direction:column; align-items:center; gap:7px; width:190px; height:190px; justify-content:center; padding:13px; border-radius:50px; border:1px solid color-mix(in srgb,var(--accent) 25%,var(--border)); background:var(--surface); color:var(--accent); box-shadow:0 18px 40px color-mix(in srgb,var(--accent) 18%,transparent); animation:edzio-hover 6s ease-in-out infinite; }.orbit-edzio > svg { width:106px; height:106px; }.orbit-edzio > strong { display:flex; align-items:center; gap:7px; font-size:19px; letter-spacing:-.4px; }.orbit-edzio > strong > span { width:6px; height:6px; border-radius:50%; background:var(--success); }.orbit-edzio > small { font-size:10px; color:var(--secondary); }.orbit-mic { position:absolute; right:calc(50% - 108px); bottom:28px; width:44px; height:44px; padding:0; border-radius:50%; background:var(--accent); color:var(--theme-on-accent,white); border:4px solid var(--surface); box-shadow:0 5px 14px color-mix(in srgb,var(--accent) 22%,transparent); }.edzio-caption { position:absolute; bottom:-16px; display:flex; align-items:center; gap:6px; font-size:10px; color:var(--secondary); white-space:nowrap; }
.orbit-greeting { display:flex; align-items:center; gap:14px; padding:17px 22px; max-width:1000px; margin:10px auto 0; border:1px solid var(--border); border-radius:17px; background:var(--surface); }.greeting-spark { display:grid; place-items:center; width:38px; height:38px; flex-shrink:0; border-radius:12px; background:var(--accent-soft); color:var(--accent); }.orbit-greeting > div { flex:1; min-width:0; }.orbit-greeting strong { font-size:12px; }.orbit-greeting p { font-size:11px; line-height:1.7; color:var(--secondary); margin:5px 0 0; }.orbit-greeting > button { flex-shrink:0; font-size:11px; color:var(--accent); background:var(--accent-soft); border:0; }
@keyframes edzio-hover { 0%,100% { transform:translateY(0); }50% { transform:translateY(-5px); } }
@media(max-width:1000px) { .orbit-board { gap:18px; grid-template-columns:minmax(0,1fr) minmax(190px,1fr) minmax(0,1fr); }.orbit-tile { padding:17px; }.orbit-node { height:auto; }.halo-two { width:235px; height:235px; } }
@media(max-width:760px) { .start-orbit { padding:20px 16px; }.orbit-board { grid-template-columns:repeat(2,minmax(0,1fr)); grid-template-rows:auto; gap:14px; }.orbit-center { grid-area:1 / 1 / auto / -1; margin:7px 0 22px; height:230px; }.orbit-node { grid-area:auto; height:auto; }.orbit-mail { grid-area:2 / 1; }.orbit-tasks { grid-area:2 / 2; }.orbit-connections { display:none; }.orbit-greeting { flex-wrap:wrap; padding:16px; }.orbit-greeting > div { flex-basis:calc(100% - 54px); }.orbit-greeting > button { margin-left:52px; }.orbit-intro h1 { font-size:26px; } }
@media(max-width:400px) { .start-orbit { padding:18px 12px; }.orbit-board { gap:10px; }.orbit-tile { padding:15px; }.orbit-tile > strong { font-size:13px; }.orbit-tile > small { font-size:10px; }.orbit-node { height:auto; min-height:156px; }.orbit-tile-arrow { top:12px; right:12px; } }
@media(prefers-reduced-motion:reduce) { .orbit-edzio { animation:none; }.orbit-node { transition:none; }.orbit-node:hover { transform:none; } }

/* Consistent dashboard cards, with a compact assistant in the middle. */
.start-orbit { container-type:inline-size; padding:26px; border-radius:22px; background:var(--surface-soft); }
.orbit-intro { text-align:left; margin-bottom:24px; }
.orbit-intro h1 { margin:9px 0; font-size:28px; letter-spacing:-.8px; }
.orbit-intro p { font-size:13px; }
.orbit-board { max-width:1000px; grid-template-columns:repeat(3,minmax(0,1fr)); grid-template-rows:repeat(3,minmax(210px,auto)); gap:16px; align-items:stretch; justify-items:stretch; padding:0; }
.orbit-connections,.edzio-halo { display:none; }
.orbit-node { width:100%; max-width:none; min-height:210px; height:100%; aspect-ratio:auto; border-radius:20px; background:var(--surface); box-shadow:0 2px 8px #20204004; transition:border-color .16s,box-shadow .16s; }
.orbit-node:hover { transform:none; border-color:color-mix(in srgb,var(--accent) 40%,var(--border)); box-shadow:0 4px 15px #20204009; }
.orbit-tile { justify-content:flex-start; gap:12px; padding:24px; }
.orbit-icon { width:44px; height:44px; border-radius:13px; }
.orbit-icon svg { width:24px; height:24px; }
.orbit-tile > strong { margin-top:5px; font-size:16px; line-height:1.35; }
.orbit-tile > small { font-size:12px; line-height:1.6; }
.orbit-tile-arrow { top:22px; right:22px; }
.orbit-badge { top:-6px; right:-8px; min-width:22px; height:22px; }
.start-orbit .orbit-mail { min-height:210px; height:100%; border-radius:20px; }
.orbit-mail :deep(.mail-card-ranges) { margin:18px 40px 0 18px; padding:3px; border-radius:9px; }
.orbit-mail :deep(.mail-card-ranges button) { padding:5px 2px; font-size:10px; }
.orbit-mail :deep(.compact-mail-open) { padding:14px 20px 18px; gap:8px; justify-content:flex-start; }
.orbit-mail :deep(.compact-mail-icon) { width:36px; height:36px; border-radius:11px; }
.orbit-mail :deep(.compact-mail-icon svg) { width:23px; height:23px; }
.orbit-mail :deep(.compact-mail-open > strong) { font-size:15px; line-height:1.35; }
.orbit-mail :deep(.compact-breakdown) { grid-template-columns:repeat(2,minmax(0,1fr)); gap:5px 10px; font-size:11px; }
.orbit-mail :deep(.compact-mail-refresh) { top:17px; right:13px; }
.orbit-center { min-height:210px; height:100%; width:100%; margin:0; border:1px solid color-mix(in srgb,var(--accent) 23%,var(--border)); border-radius:20px; background:var(--accent-soft); overflow:hidden; }
.orbit-edzio { width:100%; height:100%; min-height:210px; padding:15px 20px 36px; gap:5px; border:0; border-radius:20px; background:transparent; box-shadow:none; animation:none; }
.orbit-edzio:hover { background:color-mix(in srgb,var(--accent-soft) 80%,var(--surface)); }
.orbit-edzio > svg { width:82px; height:82px; }
.orbit-edzio > strong { font-size:18px; }
.orbit-edzio > small { font-size:11px; }
.orbit-mic { right:14px; bottom:14px; width:38px; height:38px; border:3px solid var(--surface); }
.edzio-caption { bottom:14px; left:18px; font-size:10px; }
.orbit-greeting { max-width:1000px; margin-top:20px; padding:18px 20px; border-radius:16px; }
@container(max-width:650px) {
  .orbit-board { grid-template-columns:repeat(2,minmax(0,1fr)); grid-template-rows:auto; gap:12px; }
  .orbit-center { grid-area:1 / 1 / auto / -1; min-height:155px; }
  .orbit-edzio { min-height:155px; }
  .orbit-edzio > svg { width:64px; height:64px; }
  .orbit-node { grid-area:auto; min-height:185px; }
  .orbit-mail { grid-area:2 / 1; }
  .orbit-tasks { grid-area:2 / 2; }
  .orbit-tile { padding:20px; }
}
@media(max-width:760px) {
  .start-orbit { padding:20px 16px; }
  .orbit-board { grid-template-columns:repeat(2,minmax(0,1fr)); grid-template-rows:auto; gap:12px; }
  .orbit-center { grid-area:1 / 1 / auto / -1; min-height:155px; height:100%; margin:0; }
  .orbit-edzio { min-height:155px; }
  .orbit-edzio > svg { width:64px; height:64px; }
  .orbit-node { grid-area:auto; min-height:185px; border-radius:17px; }
  .orbit-mail { grid-area:2 / 1; }
  .orbit-tasks { grid-area:2 / 2; }
  .orbit-tile { padding:20px; }
}
@media(max-width:450px) {
  .start-orbit { padding:16px 12px; }
  .orbit-intro h1 { font-size:24px; }
  .orbit-board { gap:10px; }
  .orbit-tile { padding:17px; gap:11px; }
  .orbit-tile > strong { font-size:14px; }
  .orbit-tile > small { font-size:11px; }
  .orbit-tile-arrow { top:15px; right:13px; width:15px; }
  .orbit-icon { width:38px; height:38px; border-radius:11px; }
  .orbit-mail :deep(.mail-card-ranges) { margin:14px 28px 0 10px; gap:0; padding:2px; }
  .orbit-mail :deep(.mail-card-ranges button) { font-size:9px; }
  .orbit-mail :deep(.compact-mail-refresh) { top:14px; right:5px; padding:4px; }
  .orbit-mail :deep(.compact-mail-open) { padding:12px; }
  .orbit-mail :deep(.compact-mail-open > strong) { font-size:13px; }
  .orbit-mail :deep(.compact-breakdown) { gap:4px; font-size:10px; }
  .orbit-greeting { padding:15px; }
}

</style>
