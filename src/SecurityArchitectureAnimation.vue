<script setup>
import { Shield, Server, Database, Activity } from 'lucide-vue-next'
defineProps({ paused: Boolean })
const layers = [
  { name: 'HA', label: 'Wysoka dostępność', text: 'Redundancja i ciągłość działania.', icon: Server },
  { name: 'WAF', label: 'Ochrona aplikacji', text: 'Filtrowanie podejrzanego ruchu HTTP.', icon: Shield },
  { name: 'Backup', label: 'Odtwarzanie danych', text: 'Kopie zapasowe i testy przywracania.', icon: Database },
  { name: 'SOC', label: 'Monitoring i reakcja', text: 'Analiza zdarzeń i obsługa incydentów.', icon: Activity }
]
</script>

<template>
  <section class="security-animation" :class="{ 'security-paused': paused }" aria-label="Model warstw ochrony: HA, WAF, backup i SOC">
    <header><Shield :size="19" /><strong>Warstwy cyberodporności</strong><span>Model ochrony</span></header>
    <div class="security-model">
      <svg class="security-connections" viewBox="0 0 400 300" preserveAspectRatio="none" aria-hidden="true"><path d="M80 65L200 150L320 65M80 235L200 150L320 235" /><circle cx="200" cy="150" r="46" /></svg>
      <article v-for="(layer, index) in layers" :key="layer.name" class="security-layer" :style="{ '--layer': index }"><span class="security-layer-icon"><component :is="layer.icon" :size="19" /></span><div><strong>{{ layer.name }}</strong><small>{{ layer.label }}</small></div><p>{{ layer.text }}</p></article>
      <div class="security-shield"><Shield :size="36" :stroke-width="1.3" /><span>NIS2</span></div>
    </div>
    <p class="security-model-caption">Warstwy infrastruktury i obsługi środowiska. Ich wdrożenie oraz zakres ochrony wymagają potwierdzenia.</p>
  </section>
</template>

<style scoped>
.security-animation{padding:24px;background:#f2edff;color:#725a91}.security-animation>header{display:flex;align-items:center;gap:8px;color:#9274b7;font-size:11px}.security-animation>header>strong{font-weight:550}.security-animation>header>span{margin-left:auto;font-size:8px;color:#b49ec7}.security-model{position:relative;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:84px 20px;padding:18px 0;margin:12px 0}.security-layer{position:relative;z-index:1;background:#fffdfd;border:1px solid #e4d7ef;border-radius:12px;padding:14px;display:grid;grid-template-columns:31px minmax(0,1fr);gap:8px;box-shadow:0 3px 10px #603d8a05;animation:security-layer-glow 8s ease-in-out infinite;animation-delay:calc(var(--layer)*1s)}.security-layer-icon{width:30px;height:30px;border-radius:8px;background:#f1eafb;display:grid;place-items:center;color:#a085c0}.security-layer strong{display:block;font-size:13px;color:#84679e;font-weight:600;line-height:1.4}.security-layer small{display:block;font-size:8px;line-height:1.5;margin-top:3px;color:#856b95}.security-layer p{grid-column:1/-1;margin:3px 0 0;font-size:9px;line-height:1.8;color:#80688c}.security-connections{position:absolute;inset:0;width:100%;height:100%;fill:none;stroke:#c7acde;stroke-width:1;stroke-dasharray:4 7;animation:security-link-flow 5s linear infinite}.security-shield{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);height:74px;width:74px;border-radius:50%;background:#eee4fb;border:1px solid #dcc9ed;display:flex;flex-direction:column;gap:3px;align-items:center;justify-content:center;color:#a785c2}.security-shield>span{font-size:8px;letter-spacing:1.5px}.security-model-caption{margin:4px 0 0;border-top:1px solid #e7dbf2;padding-top:14px;font-size:10px;color:#806c8c;line-height:1.8;max-width:440px}
@keyframes security-layer-glow{0%,100%{border-color:#e4d7ef}30%,50%{border-color:#b69acb;box-shadow:0 4px 12px #603d8a0b}}@keyframes security-link-flow{to{stroke-dashoffset:-44}}
.security-paused *{animation-play-state:paused!important}
@media(max-width:450px){.security-animation{padding:18px}.security-layer{padding:11px;gap:6px;grid-template-columns:26px minmax(0,1fr)}.security-layer-icon{width:25px;height:25px}.security-layer strong{font-size:12px}.security-layer small{font-size:8px}.security-layer p{font-size:9px}.security-model{gap:76px 12px}.security-animation>header{font-size:10px}.security-animation>header>span{font-size:7px}.security-shield{height:65px;width:65px}.security-shield>svg{width:30px;height:30px}}
@media(prefers-reduced-motion:reduce){.security-animation *{animation:none!important}}
</style>
