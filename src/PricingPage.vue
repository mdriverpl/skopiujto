<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeft, ArrowRight, Check, Copy, Database, Download, HardDrive, Server, Users } from 'lucide-vue-next'
import PricingNetwork from './PricingNetwork.vue'
import { boundedQuantity, calculatePricing, configurationText, databasePlans, formatMoney as money, infrastructureForPlan, serverPlans } from './pricing.js'

const form = ref(null)
const users = ref(19), storage = ref(100), selected = ref(['waf', 'backup', 'logs', 'ha'])
const serverPlan = ref('S1')
const databasePlan = ref('S1'), databaseEngine = ref('PostgreSQL'), databaseHa = ref(true)
const nis2Options = ['ha', 'logs', 'waf']
const nis2Preset = computed({
  get: () => databasePlan.value !== 'none' && databaseHa.value && nis2Options.every(id => selected.value.includes(id)),
  set: enabled => {
    if (enabled) {
      selected.value = [...new Set([...selected.value, ...nis2Options])]
      if (databasePlan.value === 'none') databasePlan.value = 'S1'
      databaseHa.value = true
    } else {
      selected.value = selected.value.filter(id => !nis2Options.includes(id))
      databaseHa.value = false
    }
  },
})
const status = ref(''), copyFallback = ref(''), copying = ref(false), preparing = ref(false)
const pricing = computed(() => calculatePricing(users.value, storage.value, selected.value, serverPlan.value,
  { planId: databasePlan.value, engine: databaseEngine.value, ha: databaseHa.value }))
const infrastructureOptions = computed(() => infrastructureForPlan(serverPlan.value))
const addons = computed(() => ['waf', 'backup', 'vpn', 'logs'].map(id => infrastructureOptions.value.find(option => option.id === id)))
const storageOptions = [100, 200, 500, 1000, 2000, 5000, 10000]
const text = () => configurationText(pricing.value)
let previousTitle
onMounted(() => {
  previousTitle = document.title
  document.title = 'Wycena · Space & Flow'
})
onBeforeUnmount(() => { document.title = previousTitle })
async function copy() {
  if (copying.value) return
  copying.value = true
  status.value = ''; copyFallback.value = ''
  try {
    await navigator.clipboard.writeText(text())
    status.value = 'Skopiowano konfigurację do schowka.'
  } catch {
    copyFallback.value = text()
    status.value = 'Schowek jest niedostępny. Zaznacz i skopiuj konfigurację poniżej.'
  } finally { copying.value = false }
}
async function prepareOffer() {
  if (preparing.value || !form.value.reportValidity()) return
  preparing.value = true
  status.value = ''
  try {
    const response = await fetch('/api/pricing/offer', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ users: pricing.value.users, storage: pricing.value.storage,
        server_plan: serverPlan.value, server_ha: selected.value.includes('ha'),
        database_plan: databasePlan.value, database_engine: databaseEngine.value, database_ha: pricing.value.database.ha,
        waf: selected.value.includes('waf'), backup: selected.value.includes('backup'), logs: selected.value.includes('logs'), vpn: selected.value.includes('vpn') }) })
    if (!response.ok || !response.headers.get('content-type')?.includes('application/pdf')) throw new Error('PDF unavailable')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url; link.download = 'SpaceFlow-oferta.pdf'
    document.body.append(link); link.click(); link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    status.value = 'Oferta PDF jest gotowa. Pobieranie rozpoczęte.'
  } catch {
    status.value = 'Nie udało się przygotować PDF. Spróbuj ponownie.'
  } finally { preparing.value = false }
}
</script>

<template>
  <div class="pricing-page">
    <main class="pricing-container" aria-labelledby="pricing-title">
      <form ref="form" class="pricing-layout" @submit.prevent="prepareOffer" @input="status = ''; copyFallback = ''">
        <aside class="pricing-summary" aria-label="Podsumowanie wyceny">
          <div class="pricing-summary-heading"><div><span class="pricing-eyebrow">DOBRE FLOW ZACZYNA SIĘ TUTAJ</span><h1 id="pricing-title">Twoja konfiguracja</h1></div><a class="pricing-back" href="/"><ArrowLeft :size="17" />Strona główna</a></div>
          <div class="pricing-nis2" title="Włącza HA bazy, HA serwera, Analizę logów i WAF. Same ustawienia techniczne nie potwierdzają pełnej zgodności z NIS2.">
            <label><input v-model="nis2Preset" type="checkbox" aria-describedby="pricing-nis2-description" /><span>Konfiguracja pod NIS2</span></label>
            <span id="pricing-nis2-description" class="pricing-sr-only">Włącza HA bazy, HA serwera, Analizę logów i WAF. Same ustawienia techniczne nie potwierdzają pełnej zgodności z NIS2.</span>
          </div>
          <table class="pricing-summary-table" aria-label="Składniki miesięcznej wyceny netto">
            <colgroup><col class="pricing-summary-icon-col" /><col /><col class="pricing-summary-ha-col" /><col class="pricing-summary-price-col" /></colgroup>
            <thead><tr><th scope="col"><span class="pricing-sr-only">Rodzaj</span></th><th scope="col">Pozycja</th><th scope="col" class="pricing-ha-cell">HA</th><th scope="col">Netto / mies.</th></tr></thead>
            <tbody>
              <tr><td><Check :size="17" aria-hidden="true" /></td><th scope="row">Cena podstawowa</th><td></td><td>{{ money(pricing.base) }}</td></tr>
              <tr><td><Users :size="17" aria-hidden="true" /></td><th scope="row"><label class="pricing-summary-users" for="pricing-summary-users">Użytkownicy<span class="pricing-summary-user-control"><input id="pricing-summary-users" v-model="users" type="number" min="1" max="500" step="1" required @change="users = boundedQuantity(users, 1, 500)" /><span>× 5 zł</span></span></label></th><td></td><td>{{ money(pricing.userCost) }}</td></tr>
              <tr>
                <td><Server :size="17" aria-hidden="true" /></td>
                <th scope="row">
                  <label class="pricing-summary-select">Serwer aplikacji<select v-model="serverPlan"><option v-for="plan in serverPlans" :key="plan.id" :value="plan.id">{{ plan.id }} · {{ plan.vcpu }} vCPU · {{ plan.ram }} GB RAM · {{ plan.nvme }} GB NVMe — {{ money(plan.monthly) }}/mies. za serwer</option></select></label>
                </th>
                <td class="pricing-ha-cell"><label class="pricing-ha-toggle"><input v-model="selected" type="checkbox" value="ha" aria-label="HA serwera aplikacji — dwa serwery" /><span>HA</span></label></td><td>{{ money(pricing.server.total) }}</td>
              </tr>
              <tr>
                <td><Database :size="17" aria-hidden="true" /></td>
                <th scope="row">
                  <label class="pricing-summary-select">Serwer bazy danych<select v-model="databasePlan"><option value="none">Brak — bez osobnego serwera bazy danych</option><option v-for="plan in databasePlans" :key="plan.id" :value="plan.id">{{ plan.id }} · {{ plan.vcpu }} vCPU · {{ plan.ram }} GB RAM · {{ plan.disk }} GB dysku — {{ money(databaseHa ? plan.ha : plan.single) }}/mies.{{ databaseHa ? ' z repliką (HA)' : '' }}</option></select></label>
                </th>
                <td class="pricing-ha-cell"><label class="pricing-ha-toggle" :class="{ 'is-disabled': !pricing.database.enabled }"><input v-model="databaseHa" type="checkbox" :disabled="!pricing.database.enabled" aria-label="HA bazy danych — z repliką" /><span>HA</span></label></td><td>{{ money(pricing.database.total) }}</td>
              </tr>
              <tr><td><HardDrive :size="17" aria-hidden="true" /></td><th scope="row"><label class="pricing-summary-select">Przestrzeń dyskowa<select v-model="storage"><option v-for="capacity in storageOptions" :key="capacity" :value="capacity">{{ capacity }} GB</option></select></label><small>20 zł / 100 GB / miesiąc</small></th><td></td><td>{{ money(pricing.disk) }}</td></tr>
              <tr v-for="option in addons" :key="option.id"><td><input :id="'pricing-addon-' + option.id" v-model="selected" type="checkbox" :value="option.id" :aria-describedby="'pricing-addon-description-' + option.id" /></td><th scope="row"><label :for="'pricing-addon-' + option.id">{{ option.name }}</label><small :id="'pricing-addon-description-' + option.id">{{ option.description }} · {{ money(option.price) }}/mies.</small></th><td></td><td>{{ money(selected.includes(option.id) ? option.price : 0) }}</td></tr>
            </tbody>
          </table>
          <div class="pricing-total" aria-live="polite" aria-atomic="true"><span>Miesięcznie netto</span><strong>{{ money(pricing.total) }}</strong></div>
          <p class="pricing-disclaimer">Ceny demonstracyjne • + VAT • wdrożenie wyceniane osobno</p>
          <button class="pricing-submit" type="submit" :disabled="preparing">{{ preparing ? 'Przygotowywanie PDF…' : 'Przygotuj ofertę PDF' }} <ArrowRight :size="18" /></button>
          <button class="pricing-copy" type="button" :disabled="copying" @click="copy"><Copy :size="16" />Kopiuj konfigurację</button>
          <p class="pricing-export-note"><Download :size="14" /> Oferta do pobrania w pliku PDF</p>
          <p v-if="status" class="pricing-status" role="status">{{ status }}</p>
          <label v-if="copyFallback" class="pricing-fallback">Konfiguracja do skopiowania<textarea :value="copyFallback" readonly rows="8" @focus="event => event.target.select()" /></label>
        </aside>
      </form>
      <PricingNetwork :pricing="pricing" :selected="selected" />
    </main>
  </div>
</template>

<style scoped>
.pricing-page{--text:#30233f;--secondary:#80718e;--border:#e8dff1;--surface:#fff;--focus-ring:#b699ee;--accent-soft:#f1eaff;color:var(--text);background:#fcfaff;font-family:Inter,system-ui,sans-serif;min-height:100dvh;padding:32px 16px;color-scheme:light}.pricing-container{width:min(740px,100%);max-width:none;margin:0 auto;padding:0}
.pricing-page *{box-sizing:border-box}.pricing-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;padding:25px 30px;border-bottom:1px solid var(--border);background:#fcfaff}.pricing-eyebrow{font-size:9px;letter-spacing:1.7px;font-weight:700;color:#9066ba}.pricing-heading h2{font-size:27px;letter-spacing:-1px;margin:8px 0}.pricing-heading p{font-size:12px;color:var(--secondary);margin:0;line-height:1.7}.pricing-close{padding:8px;background:#fff;flex-shrink:0}.pricing-layout{padding:24px}.pricing-summary{padding:24px;background:linear-gradient(155deg,#f5edff,#faf7ff);border:1px solid #e8daf6;border-radius:18px}.pricing-summary>.pricing-eyebrow{font-size:9px}.pricing-summary h3{font-size:22px;margin:12px 0 22px;letter-spacing:-.7px}
.pricing-summary-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px;text-align:left}.pricing-summary-icon-col{width:28px}.pricing-summary-ha-col{width:48px}.pricing-summary-price-col{width:106px}.pricing-summary-table thead th{font-size:10px;font-weight:500;color:var(--secondary);padding:0 0 10px;border-bottom:1px solid #e2d3ef}.pricing-summary-table thead th:last-child{text-align:right;white-space:nowrap}.pricing-summary-table tbody th,.pricing-summary-table tbody td{padding:12px 0;border-bottom:1px solid #e8ddf2;vertical-align:middle;line-height:1.5}.pricing-summary-table tbody th{font-weight:400;padding-right:12px;overflow-wrap:anywhere}.pricing-summary-table tbody td:last-child{text-align:right;font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}.pricing-summary-table tbody tr:last-child>*{border-bottom:0}.pricing-summary-table svg{display:block;color:#ab8bc7}.pricing-summary-table label{display:block;cursor:pointer}.pricing-summary-table small{display:block;font-size:10px;color:var(--secondary);margin-top:4px;line-height:1.6}.pricing-summary-select select{display:block;width:100%;min-width:0;max-width:100%;margin-top:7px;padding:8px;border:1px solid #ddcbea;border-radius:8px;background:#fff9;color:var(--text);font-size:12px;cursor:pointer}.pricing-summary-table input[type=checkbox]{display:block;width:17px;height:17px;margin:0;accent-color:#8946d7;cursor:pointer}.pricing-ha-cell{text-align:center}.pricing-summary-table .pricing-ha-cell input{margin-inline:auto}.pricing-summary-table input:disabled{opacity:.35;cursor:default}.pricing-summary-user-control{display:flex;align-items:center;gap:8px;margin-top:7px}.pricing-summary-user-control input{width:76px;min-width:0;padding:7px;border:1px solid #ddcbea;border-radius:8px;background:#fff9;color:var(--text);font-size:12px;text-align:center}.pricing-summary-user-control>span{white-space:nowrap;color:var(--secondary);font-size:11px}
.pricing-total{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:18px;border-top:1px solid #e2d3ef;padding-top:20px}.pricing-total>span{font-size:12px;color:#806b91}.pricing-total>strong{font-size:38px;letter-spacing:-1.7px;color:#7737c2;overflow-wrap:anywhere}.pricing-disclaimer{font-size:10px;line-height:1.8;color:#8e7a9e;margin:13px 0 22px}.pricing-submit,.pricing-copy{width:100%;font-size:12px;padding:13px 10px}.pricing-submit{background:linear-gradient(115deg,#a44bf0,#6d31f5);color:#fff;border:0;justify-content:space-between}.pricing-submit:hover{background:#7737c2}.pricing-copy{margin-top:9px;background:#fff;border-color:#e5d8f1;color:#785791}.pricing-export-note{display:flex;align-items:center;justify-content:center;gap:6px;font-size:10px;color:#9b86ad;margin:14px 0 0}.pricing-status{font-size:12px;line-height:1.7;color:#655078;overflow-wrap:anywhere}.pricing-fallback{display:grid;gap:8px;font-size:11px;color:#71617f;margin-top:15px}.pricing-fallback textarea{font-size:11px;width:100%}.pricing-sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;border:0}
@media(max-width:520px){.pricing-page{padding:12px 0}.pricing-heading{padding:20px 16px}.pricing-layout{padding:12px}.pricing-summary{padding:15px 12px}.pricing-summary h3{font-size:20px}.pricing-summary-icon-col{width:23px}.pricing-summary-ha-col{width:32px}.pricing-summary-price-col{width:77px}.pricing-summary-table{font-size:11px}.pricing-summary-table tbody th{padding-right:7px}.pricing-summary-select select{font-size:11px;padding:7px 3px}.pricing-summary-table small{font-size:9px}.pricing-summary-table thead th{font-size:9px}.pricing-total{align-items:flex-start;flex-direction:column;gap:6px}.pricing-total>strong{font-size:34px}}
.pricing-summary-ha-col{width:64px}.pricing-summary-table .pricing-ha-toggle{display:inline-flex;align-items:center;justify-content:center;gap:5px;font-size:12px;font-weight:600;white-space:nowrap;color:#68428b}.pricing-summary-table .pricing-ha-cell .pricing-ha-toggle input{margin:0}.pricing-ha-toggle.is-disabled{opacity:.5;cursor:default}
@media(max-width:520px){.pricing-summary-ha-col{width:51px}.pricing-summary-table .pricing-ha-toggle{font-size:11px;gap:4px}}
.pricing-nis2{padding:13px 15px;margin:0 0 20px;border:1px solid #cdb3e6;border-radius:11px;background:#fff8}.pricing-nis2 label{display:flex;align-items:center;gap:9px;font-size:13px;font-weight:600;color:#68428b;cursor:pointer}.pricing-nis2 input{width:18px;height:18px;flex-shrink:0;margin:0;accent-color:#8946d7}.pricing-nis2 p{font-size:10px;line-height:1.7;color:var(--secondary);margin:7px 0 0}
.pricing-summary-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:20px}.pricing-summary-heading h1{font-size:22px;margin:12px 0 0;letter-spacing:-.7px}.pricing-summary-heading .pricing-close{font-size:11px;padding:8px 10px;white-space:nowrap}
@media(max-width:520px){.pricing-summary-heading h1{font-size:20px}.pricing-summary-heading .pricing-close{padding:7px;font-size:10px}.pricing-summary-heading .pricing-eyebrow{font-size:8px}}
.pricing-nis2{padding:7px 10px;margin-bottom:14px;border-radius:8px}.pricing-nis2 label{gap:7px;font-size:11px;line-height:1.4;white-space:nowrap}.pricing-nis2 input{width:15px;height:15px}
.pricing-back{display:inline-flex;align-items:center;gap:6px;font-size:11px;padding:8px 10px;border:1px solid #ddcbea;border-radius:8px;background:#fff;color:#68428b;text-decoration:none;white-space:nowrap}.pricing-back:hover{background:#f1eaff}@media(max-width:420px){.pricing-summary-heading{flex-wrap:wrap}.pricing-back{font-size:10px}}
.pricing-container{width:min(1260px,100%);display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,1fr);gap:24px;align-items:start}.pricing-layout{padding:0;min-width:0}.pricing-summary{padding:24px}
@media(max-width:1100px){.pricing-container{width:min(740px,100%);grid-template-columns:minmax(0,1fr)}}
@media(max-width:520px){.pricing-container{gap:12px;padding:0 12px}.pricing-summary{padding:15px 12px}}
</style>
