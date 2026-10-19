<script setup>
import { BellRing, Smartphone, Users, ListChecks, ArrowDown } from 'lucide-vue-next'
defineProps({ paused: Boolean })
</script>

<template>
  <div class="alert-demo" :class="{ 'alert-paused': paused }" role="img" aria-label="Przykład: nauczyciel wybiera kod alertu, pozostali nauczyciele otrzymują powiadomienie i procedurę szkoły.">
    <div class="alert-demo-heading"><BellRing :size="21" /><strong>Alert dla nauczycieli</strong><span>Przykład</span></div>
    <div class="alert-demo-step alert-demo-code"><span class="alert-demo-icon"><Smartphone :size="25" /></span><div><small>1 / NAUCZYCIEL</small><strong>Wybór kodu alertu</strong><p>Kod ustalony przez szkołę</p></div><b>KOD A</b></div>
    <ArrowDown class="alert-demo-arrow" :size="20" />
    <div class="alert-demo-step alert-demo-notice"><span class="alert-demo-icon"><Users :size="25" /></span><div><small>2 / POZOSTALI NAUCZYCIELE</small><strong>Powiadomienie o alercie</strong><p>Ten sam kod dla wszystkich odbiorców</p></div><BellRing class="alert-demo-bell" :size="24" /></div>
    <ArrowDown class="alert-demo-arrow" :size="20" />
    <div class="alert-demo-step alert-demo-procedure"><span class="alert-demo-icon"><ListChecks :size="25" /></span><div><small>3 / PROCEDURA SZKOŁY</small><strong>Co zrobić po otrzymaniu alertu</strong><p>Instrukcja przypisana do wybranego kodu</p></div></div>
    <p class="alert-demo-note">Przykładowy kod. Kody i procedury określa szkoła.</p>
  </div>
</template>

<style scoped>
.alert-demo{padding:24px;background:#faf5ff;color:#514260}
.alert-demo-heading{display:flex;align-items:center;gap:10px;margin-bottom:24px;color:#8051b1;font-size:12px}
.alert-demo-heading>span{margin-left:auto;font-size:9px;color:#9b8ba9}
.alert-demo-step{display:flex;align-items:center;gap:13px;padding:18px 16px;border:1px solid #e6d9ee;border-radius:15px;background:#fff;animation:alert-arrive 6s ease-in-out infinite}
.alert-demo-step>div{flex:1;min-width:0}.alert-demo-step small{display:block;font-size:8px;letter-spacing:1px;color:#947caa;margin-bottom:7px}
.alert-demo-step strong{display:block;font-size:13px;font-weight:600;line-height:1.5}.alert-demo-step p{font-size:10px;line-height:1.6;color:#8b7999;margin:5px 0 0}
.alert-demo-icon{display:grid;place-items:center;flex-shrink:0;width:43px;height:43px;border-radius:12px;background:#f3ebfc;color:#8b59c2}
.alert-demo-code>b{padding:8px;border:1px solid #ebcebd;border-radius:8px;background:#fff5ed;color:#a36a4e;font-size:11px;white-space:nowrap}
.alert-demo-arrow{display:block;margin:9px auto;color:#c2a4d4}
.alert-demo-notice{animation-delay:1s;border-color:#e3c3cd}.alert-demo-notice .alert-demo-icon{background:#fcecf0;color:#b16a82}
.alert-demo-bell{flex-shrink:0;color:#b16a82;animation:alert-ring 6s ease-in-out infinite}
.alert-demo-procedure{animation-delay:2s}.alert-demo-procedure .alert-demo-icon{background:#ecf5ef;color:#6c947e}
.alert-demo-note{font-size:9px;line-height:1.7;text-align:center;margin:18px 0 0;color:#9784a5}
@keyframes alert-arrive{0%,12%,70%,100%{transform:translateY(0);box-shadow:0 0 0 transparent}25%,48%{transform:translateY(-3px);box-shadow:0 7px 20px #8051b112}}
@keyframes alert-ring{0%,22%,38%,100%{transform:rotate(0)}26%,34%{transform:rotate(12deg)}30%{transform:rotate(-12deg)}}
.alert-paused *{animation-play-state:paused}
@media(max-width:440px){.alert-demo{padding:18px 12px}.alert-demo-step{padding:14px 10px;gap:9px}.alert-demo-icon{width:32px;height:38px}.alert-demo-icon svg{width:21px}.alert-demo-step strong{font-size:11px}.alert-demo-step small{font-size:7px}.alert-demo-step p{font-size:9px}.alert-demo-code>b{font-size:9px;padding:6px}}
@media(prefers-reduced-motion:reduce){.alert-demo *{animation:none}}
</style>
