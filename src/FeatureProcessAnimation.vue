<script setup>
import { computed } from 'vue'
import { Check, FileText, Users, ShieldCheck, ClipboardCheck, ArrowRight } from 'lucide-vue-next'
import EdzioAvatar from './EdzioAvatar.vue'
const props = defineProps({ mode: String, paused: Boolean })
const demo = computed(() => ({
  tasks: { title: 'Każde zadanie ma następny krok', icon: ClipboardCheck, stages: ['Do zrobienia', 'W toku', 'Gotowe'], cards: ['Sprawdź dokument', 'Przygotuj odpowiedź', 'Domknij sprawę'], hint: 'Przydziel. Zaplanuj. Sprawdź postęp.' },
  collaboration: { title: 'Dobry przepływ między ludźmi', icon: Users, stages: ['Przygotuj', 'Udostępnij', 'Zaakceptuj'], cards: ['Umowa do akceptacji', 'Ustalenia zespołu', 'Odpowiedź w ankiecie'], hint: 'Właściwe osoby. Wspólny kontekst.' },
  edelivery: { title: 'Korespondencja urzędowa w porządku', icon: ShieldCheck, stages: ['Przesyłka', 'Twój rejestr', 'Status'], cards: ['Nowa korespondencja', 'Metadane przesyłki', 'Aktualizacja statusu'], hint: 'Sprawdzaj rejestr i statusy po podłączeniu skrzynki.' }
}[props.mode] || { title: 'Dobry przepływ pracy', icon: FileText, stages: ['Dodaj', 'Uporządkuj', 'Gotowe'], cards: ['Nowa sprawa', 'Ważny dokument', 'Kolejny krok'], hint: 'Każda sprawa na swoim miejscu.' }))
</script>

<template>
  <div class="feature-process" :class="{ 'process-paused': paused }">
    <div class="process-heading"><component :is="demo.icon" :size="22" /><strong>{{ demo.title }}</strong><span>Przykład</span></div>
    <div class="process-stage" role="img" :aria-label="demo.cards.join(', ') + '. Przepływ: ' + demo.stages.join(', ')">
      <div class="process-columns"><div v-for="(stage, i) in demo.stages" :key="stage"><span :class="'process-dot-' + i"></span>{{ stage }}<ArrowRight v-if="i !== 2" :size="13" /></div></div>
      <div class="process-guides"><span></span><span></span><span></span></div>
      <div v-for="(card, i) in demo.cards" :key="card" class="process-moving-card" :style="{ '--card-order': i }"><span><FileText :size="18" /></span><strong>{{ card }}</strong><Check :size="15" /></div>
      <span class="process-complete"><Check :size="15" /> Sprawa idzie do przodu.</span>
    </div>
    <div class="process-edzio"><EdzioAvatar /><div><strong>Edzio AI</strong><span>{{ demo.hint }}</span></div></div>
  </div>
</template>

<style scoped>
.feature-process{background:#f2edff;padding:24px;color:#665180}.process-heading{display:flex;align-items:center;gap:10px;font-size:11px;color:#7756b5}.process-heading strong{font-weight:550;line-height:1.5}.process-heading>span{margin-left:auto;font-size:8px;color:#a091b5}.process-stage{position:relative;height:285px;margin-top:25px;overflow:hidden;border:1px solid #e2d8f0;background:#faf8ff;border-radius:14px}.process-columns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));position:relative;z-index:1;background:#f9f5ff;border-bottom:1px solid #e9e0f4}.process-columns>div{display:flex;align-items:center;gap:5px;justify-content:center;padding:15px 3px;font-size:9px;color:#9a86ae}.process-columns>div>span{width:5px;height:5px;border-radius:50%;background:#cfb9e9}.process-columns>div>.process-dot-1{background:#d5c093}.process-columns>div>.process-dot-2{background:#9fbd9b}.process-columns svg{margin-left:7px;opacity:.5}.process-guides{position:absolute;inset:42px 0 0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}.process-guides>span{border-right:1px dashed #e4daed}.process-guides>span:last-child{border-right:0}.process-moving-card{position:absolute;top:calc(68px + var(--card-order)*55px);left:4%;width:45%;display:flex;align-items:center;gap:8px;padding:12px 10px;background:white;border:1px solid #e2d7ee;border-radius:8px;box-shadow:0 3px 8px #6f4c9310;animation:process-card-forward 10s cubic-bezier(.35,.1,.25,1) infinite;animation-delay:calc(var(--card-order)*.55s)}.process-moving-card>span{width:25px;height:25px;border-radius:7px;display:grid;place-items:center;flex-shrink:0;background:#f0e7fc;color:#a086bd}.process-moving-card>strong{font-weight:500;font-size:9px;line-height:1.5}.process-moving-card>svg{margin-left:auto;flex-shrink:0;color:#94ad88;animation:process-check 10s infinite;animation-delay:calc(var(--card-order)*.55s)}.process-complete{position:absolute;bottom:12px;left:16px;font-size:9px;color:#a1ac91;display:flex;align-items:center;gap:6px}.process-edzio{display:flex;align-items:center;gap:12px;margin-top:17px}.process-edzio>svg{width:47px;height:47px;--surface:#fff;color:#7455c8}.process-edzio>div{display:grid;gap:4px}.process-edzio strong{font-size:11px;color:#7b5fa5}.process-edzio span{font-size:9px;line-height:1.5;color:#a28eb4}
@keyframes process-card-forward{0%,5%{opacity:0;transform:translateX(0) rotate(-3deg)}12%,22%{opacity:1;transform:translateX(0) rotate(0)}42%,50%{opacity:1;transform:translateX(54%) rotate(0)}70%,88%{opacity:1;transform:translateX(110%) rotate(0);border-color:#c4d7b8}96%,100%{opacity:0;transform:translateX(110%) rotate(0)}}@keyframes process-check{0%,55%,100%{opacity:0}70%,90%{opacity:1}}
.process-paused *{animation-play-state:paused!important}
@media(max-width:450px){.feature-process{padding:18px}.process-heading{font-size:10px;gap:7px}.process-moving-card{gap:5px;padding:10px 7px}.process-moving-card>strong{font-size:8px}.process-moving-card>span{width:21px;height:21px}.process-moving-card>svg{width:12px}.process-columns>div{font-size:8px}.process-columns svg{margin-left:2px;width:10px}}
@media(prefers-reduced-motion:reduce){.feature-process *{animation:none!important}.process-moving-card{transform:translateX(110%);opacity:1}.process-moving-card>svg{opacity:1}}
</style>
