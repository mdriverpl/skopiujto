<script setup>
import { computed } from 'vue'
import { FileText, CalendarDays, ClipboardCheck, Mail, ShieldCheck } from 'lucide-vue-next'
import BrandMark from './BrandMark.vue'
import EdzioAvatar from './EdzioAvatar.vue'
const props = defineProps({ paused: Boolean, mode: { type: String, default: 'home' } })
const baseShelves = [
  { title: 'Dokumenty', hint: 'Pliki i umowy', icon: FileText, y: 63, color: '#8ed8e4', flight: 'documents' },
  { title: 'Terminy', hint: 'Wszystko na czas', icon: CalendarDays, y: 145, color: '#e4c28c', flight: 'dates' },
  { title: 'Zadania', hint: 'Każda sprawa ma plan', icon: ClipboardCheck, y: 227, color: '#a9d2ac', flight: 'tasks' },
  { title: 'Wiadomości', hint: 'Ustalenia pod ręką', icon: Mail, y: 309, color: '#bcb3ed', flight: 'messages' }
]
const shelves = computed(() => {
  const definitions = {
    documents: [['Umowy', 'Wszystkie wersje razem', FileText], ['Faktury', 'Łatwo wrócić do pliku', FileText], ['Oferty', 'Przy każdej sprawie', FileText], ['Pozostałe pliki', 'Każdy na swoim miejscu', FileText]],
    messages: [['Odebrane', 'Nowe sprawy w jednym miejscu', Mail], ['e-Doręczenia', 'Rejestr i statusy przesyłek', ShieldCheck], ['Do odpowiedzi', 'Ustalenia pod ręką', Mail], ['Archiwum', 'Historia korespondencji', Mail]]
  }
  const variant = definitions[props.mode]
  return baseShelves.map((shelf, i) => variant ? { ...shelf, title: variant[i][0], hint: variant[i][1], icon: variant[i][2] } : shelf)
})
</script>

<template>
  <div class="flow-shelf-animation" :class="{ 'shelf-paused': paused }">
    <svg class="shelf-scene" viewBox="0 0 720 470" role="img" aria-labelledby="shelf-scene-title shelf-scene-description">
      <title id="shelf-scene-title">Edzio AI pomaga uporządkować Twoją przestrzeń</title>
      <desc id="shelf-scene-description">{{ 'Wiatrak kieruje pliki od lewej do prawej na półki: ' + shelves.map(shelf => shelf.title).join(', ') + '.' }}</desc>
      <defs>
        <linearGradient id="shelf-rack-fill" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".075" /><stop offset="1" stop-color="#fff" stop-opacity=".015" /></linearGradient>
        <radialGradient id="shelf-fan-glow"><stop offset="0" stop-color="#51cbed" stop-opacity=".25" /><stop offset="1" stop-color="#51cbed" stop-opacity="0" /></radialGradient>
      </defs>
      <circle cx="114" cy="350" r="142" fill="url(#shelf-fan-glow)" />
      <g class="shelf-orbit-rings" fill="none" stroke="#8bcbea"><circle cx="114" cy="350" r="84" /><circle cx="114" cy="350" r="136" /><circle cx="114" cy="350" r="190" /></g>
      <g class="shelf-wind-trails" fill="none" stroke="#8ed3eb" stroke-width="1.4">
        <path d="M158 327C245 235 350 105 548 96" />
        <path d="M165 342C295 275 370 183 548 178" />
        <path d="M170 357C290 338 393 273 548 260" />
        <path d="M170 373C300 395 413 365 548 342" />
      </g>

      <g class="shelf-edzio">
        <rect x="38" y="42" width="206" height="131" rx="22" fill="#f7f8ff" fill-opacity=".97" />
        <EdzioAvatar x="52" y="54" width="74" height="74" class="shelf-edzio-avatar" />
        <text x="136" y="87" class="shelf-edzio-name">Edzio<tspan dx="5" class="shelf-ai-label">AI</tspan></text>
        <circle cx="139" cy="105" r="3" fill="#699b89" />
        <text x="149" y="108" class="shelf-edzio-status">Twój pomocnik</text>
        <text x="58" y="145" class="shelf-edzio-caption">Spokojnie. Zrobimy tu porządek.</text>
        <path d="M76 173L91 188L101 173" fill="#f7f8ff" />
      </g>

      <g class="shelf-rack">
        <rect x="374" y="35" width="318" height="372" rx="19" fill="url(#shelf-rack-fill)" stroke="#d1e6fa" stroke-opacity=".19" />
        <text x="395" y="23" class="shelf-rack-heading">TWOJA PRZESTRZEŃ</text>
        <g v-for="(shelf, i) in shelves" :key="shelf.title" :style="{ '--shelf-color': shelf.color, '--shelf-index': i }" class="shelf-row">
          <rect x="391" :y="shelf.y" width="284" height="66" rx="8" fill="#fff" fill-opacity=".035" />
          <component :is="shelf.icon" x="406" :y="shelf.y + 13" width="20" height="20" :stroke="shelf.color" :stroke-width="1.5" />
          <text x="437" :y="shelf.y + 27" class="shelf-category">{{ shelf.title }}</text>
          <text x="437" :y="shelf.y + 45" class="shelf-category-hint">{{ shelf.hint }}</text>
          <path :d="'M391 ' + (shelf.y + 67) + 'H675'" stroke="#c2d9f2" stroke-opacity=".42" stroke-width="2.5" />
          <path :d="'M400 ' + (shelf.y + 70) + 'V' + (shelf.y + 76) + 'M666 ' + (shelf.y + 70) + 'V' + (shelf.y + 76)" stroke="#c2d9f2" stroke-opacity=".2" stroke-width="3" />
          <g v-for="book in 3" :key="book" class="shelf-book" :style="{ '--book-index': book }">
            <rect :x="578 + book * 20" :y="shelf.y + 22 - book * 2" width="14" :height="42 + book * 2" rx="2.5" :fill="shelf.color" :fill-opacity=".4 + book * .15" />
            <path :d="'M' + (582 + book * 20) + ' ' + (shelf.y + 31) + 'h6'" stroke="#fff" stroke-opacity=".55" />
            <circle :cx="585 + book * 20" :cy="shelf.y + 54" r="1.6" fill="#fff" fill-opacity=".6" />
          </g>
        </g>
      </g>

      <g v-for="(shelf, i) in shelves" :key="'flight-' + shelf.title" class="shelf-flying-paper" :class="'flight-' + shelf.flight" :style="{ '--flight-index': i, '--destination-y': (shelf.y + 34) + 'px' }">
        <rect x="-18" y="-24" width="36" height="47" rx="4" fill="#f9fcff" stroke="#d7e1f3" />
        <path d="M8-24V-13H18" fill="#e5eaf6" stroke="#cbd7ea" stroke-width="1" />
        <component :is="shelf.icon" x="-11" y="-10" width="21" height="21" :stroke="shelf.color === '#e4c28c' ? '#b99052' : shelf.color === '#a9d2ac' ? '#709875' : '#7e8fbe'" :stroke-width="1.7" />
        <path d="M-10 16H8" stroke="#d2daeb" stroke-width="1.5" stroke-linecap="round" />
      </g>

      <g class="shelf-fan">
        <circle cx="114" cy="350" r="53" fill="#0d2e63" stroke="#7bc8e8" stroke-opacity=".23" />
        <BrandMark x="68" y="304" width="92" height="92" class="shelf-fan-mark" />
        <text x="114" y="425" text-anchor="middle" class="shelf-fan-caption">ŁAPIEMY DOBRE FLOW</text>
      </g>
      <g class="shelf-flow-label"><circle cx="287" cy="436" r="3" fill="#82bdc8" /><text x="300" y="440">Od luźnych spraw do porządku.</text></g>
    </svg>
  </div>
</template>

<style scoped>
.flow-shelf-animation{width:100%;overflow:hidden}.shelf-scene{display:block;width:100%;height:auto;overflow:visible}.shelf-orbit-rings{opacity:.12;stroke-width:1}.shelf-wind-trails{opacity:.35;stroke-dasharray:4 10;animation:shelf-wind-flow 3s linear infinite}.shelf-edzio-avatar{color:#6b56d9;--surface:#fff}.shelf-edzio-name{font:600 20px Inter,system-ui,sans-serif;fill:#6553b5;letter-spacing:-.5px}.shelf-ai-label{font-size:10px;fill:#9b8cc8;letter-spacing:1px}.shelf-edzio-status{font:10px Inter,system-ui,sans-serif;fill:#9a8faa}.shelf-edzio-caption{font:10px Inter,system-ui,sans-serif;fill:#86769f}.shelf-edzio{animation:shelf-edzio-bob 7s ease-in-out infinite;transform-origin:140px 110px}.shelf-rack-heading{font:8px Inter,system-ui,sans-serif;letter-spacing:2.2px;fill:#c7deef;opacity:.65}.shelf-category{font:550 13px Inter,system-ui,sans-serif;fill:#edf6ff}.shelf-category-hint{font:9px Inter,system-ui,sans-serif;fill:#c1d2e8;opacity:.65}.shelf-fan-mark{color:#50c9ee}.shelf-fan-mark :deep(.space-flow-rotor){animation:shelf-fan-turn 3.5s linear infinite;transform-origin:24px 24px}.shelf-fan-caption{font:7px Inter,system-ui,sans-serif;fill:#99c8e3;letter-spacing:2px}.shelf-flow-label text{font:10px Inter,system-ui,sans-serif;fill:#a9c9e0}.shelf-book{animation:shelf-book-arrive 12s ease-in-out infinite;animation-delay:calc(var(--shelf-index)*.4s + var(--book-index)*.16s)}.shelf-flying-paper{opacity:0;transform:translate(565px,var(--destination-y));animation-duration:12s;animation-iteration-count:infinite;animation-timing-function:cubic-bezier(.35,.1,.25,1);animation-delay:calc(var(--flight-index)*.4s);transform-origin:0 0}.flight-documents{animation-name:shelf-to-documents}.flight-dates{animation-name:shelf-to-dates}.flight-tasks{animation-name:shelf-to-tasks}.flight-messages{animation-name:shelf-to-messages}
@keyframes shelf-fan-turn{to{transform:rotate(-360deg)}}@keyframes shelf-wind-flow{to{stroke-dashoffset:-42}}@keyframes shelf-edzio-bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}@keyframes shelf-book-arrive{0%,27%,100%{opacity:.12;transform:translateY(-2px)}45%,88%{opacity:1;transform:translateY(0)}}
@keyframes shelf-to-documents{0%,6%{opacity:0;transform:translate(140px,328px) rotate(-32deg) scale(.65)}12%{opacity:1}28%{transform:translate(285px,156px) rotate(14deg) scale(1)}48%,58%{opacity:1;transform:translate(565px,97px) rotate(0) scale(.8)}66%,100%{opacity:0;transform:translate(606px,104px) rotate(0) scale(.55)}}
@keyframes shelf-to-dates{0%,10%{opacity:0;transform:translate(145px,340px) rotate(24deg) scale(.65)}17%{opacity:1}34%{transform:translate(302px,227px) rotate(-16deg) scale(1)}53%,63%{opacity:1;transform:translate(565px,179px) rotate(0) scale(.8)}71%,100%{opacity:0;transform:translate(606px,186px) rotate(0) scale(.55)}}
@keyframes shelf-to-tasks{0%,14%{opacity:0;transform:translate(147px,351px) rotate(-22deg) scale(.65)}21%{opacity:1}40%{transform:translate(310px,303px) rotate(13deg) scale(1)}58%,68%{opacity:1;transform:translate(565px,261px) rotate(0) scale(.8)}76%,100%{opacity:0;transform:translate(606px,268px) rotate(0) scale(.55)}}
@keyframes shelf-to-messages{0%,18%{opacity:0;transform:translate(145px,365px) rotate(21deg) scale(.65)}25%{opacity:1}45%{transform:translate(310px,380px) rotate(-12deg) scale(1)}63%,73%{opacity:1;transform:translate(565px,343px) rotate(0) scale(.8)}81%,100%{opacity:0;transform:translate(606px,350px) rotate(0) scale(.55)}}
.shelf-paused *,.shelf-paused :deep(.space-flow-rotor){animation-play-state:paused!important}
@media(prefers-reduced-motion:reduce){.flow-shelf-animation *,.flow-shelf-animation :deep(.space-flow-rotor){animation:none!important}.shelf-flying-paper{opacity:1;transform:translate(565px,var(--destination-y)) scale(.8)}.shelf-book{opacity:1}.shelf-wind-trails{opacity:.2}}
</style>
