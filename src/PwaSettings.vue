<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { Bell, Download, MonitorSmartphone, Trash2, X } from 'lucide-vue-next'
import { installAvailable, installed, installPwa, registerPwa, applicationServerKey } from './pwa.js'

const props = defineProps({ api: { type: Function, required: true } })
const emit = defineEmits(['close'])
const dialog = ref(null)
const previousFocus = document.activeElement
function trapFocus(event) {
  if (event.key !== 'Tab') return
  const elements = [...dialog.value.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href]')]
  const first = elements[0], last = elements[elements.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
const busy = ref(false), error = ref(''), notice = ref(''), devices = ref([])
const config = ref(null), currentId = ref(null)
const name = ref(/Android/i.test(navigator.userAgent) ? 'Telefon Android' : /Windows/i.test(navigator.userAgent) ? 'Komputer Windows' : 'Moje urządzenie')
const preferences = ref({ messages: true, tasks: true, reminders: true })
const permission = ref('Notification' in window ? Notification.permission : 'unsupported')
const supported = computed(() => window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && permission.value !== 'unsupported')
const current = computed(() => devices.value.find(device => device.id === currentId.value))

async function run(action) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await action() } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
async function load() {
  const [configuration, list] = await Promise.all([props.api('/push/config'), props.api('/push/subscriptions')])
  config.value = configuration; devices.value = list
  try { currentId.value = localStorage.getItem('edokumenty-push-id') } catch {}
  if (current.value) {
    name.value = current.value.name
    preferences.value = Object.fromEntries(['messages', 'tasks', 'reminders'].map(key => [key, !!current.value[key]]))
  }
}
async function enable() {
  if (!supported.value || !config.value?.configured || busy.value) return
  // Request directly from a click before network requests consume the user gesture.
  const granted = await Notification.requestPermission()
  permission.value = granted
  if (granted !== 'granted') {
    error.value = 'Zezwól na powiadomienia w ustawieniach tej witryny w przeglądarce.'
    return
  }
  await run(async () => {
    const registration = await registerPwa()
    let subscription = await registration.pushManager.getSubscription()
    let created = false
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: applicationServerKey(config.value.public_key) })
      created = true
    }
    try {
      const result = await props.api('/push/subscriptions', 'POST', { ...subscription.toJSON(), name: name.value, ...preferences.value })
      try { localStorage.setItem('edokumenty-push-id', result.id) } catch {}
      currentId.value = result.id
      await load()
      notice.value = 'Powiadomienia zostały włączone na tym urządzeniu.'
    } catch (failure) {
      if (created) await subscription.unsubscribe().catch(() => {})
      throw failure
    }
  })
}
async function remove(device) {
  await run(async () => {
    await props.api('/push/subscriptions/' + device.id, 'DELETE')
    if (device.id === currentId.value) {
      const registration = await navigator.serviceWorker.getRegistration()
      const subscription = await registration?.pushManager.getSubscription()
      await subscription?.unsubscribe()
      try { localStorage.removeItem('edokumenty-push-id') } catch {}
      currentId.value = null
    }
    await load()
    notice.value = 'Powiadomienia dla urządzenia zostały wyłączone.'
  })
}
async function save() {
  await run(async () => {
    await props.api('/push/subscriptions/' + currentId.value, 'PATCH', { ...preferences.value, name: name.value })
    await load(); notice.value = 'Ustawienia zostały zapisane.'
  })
}
async function test() {
  await run(async () => {
    await props.api('/push/subscriptions/' + currentId.value + '/test', 'POST')
    notice.value = 'Test wysłany. Sprawdź powiadomienia systemowe.'
  })
}
onMounted(() => { dialog.value?.querySelector('button')?.focus(); run(load) })
onBeforeUnmount(() => previousFocus?.focus())
</script>

<template>
  <section ref="dialog" class="panel pwa-settings" @keydown="trapFocus" role="dialog" aria-modal="true" aria-labelledby="pwa-title" @keydown.esc="emit('close')">
    <header><div><span class="eyebrow">Android i Windows</span><h2 id="pwa-title"><MonitorSmartphone :size="23" /> Aplikacja i powiadomienia</h2></div><button class="icon-button" aria-label="Zamknij ustawienia aplikacji" @click="emit('close')"><X :size="21" /></button></header>
    <p v-if="error" role="alert" class="pwa-error">{{ error }}</p><p v-if="notice" role="status">{{ notice }}</p>
    <section class="pwa-block"><h3>Zainstaluj eDokumenty</h3><p>Otwieraj aplikację z ekranu telefonu, pulpitu lub menu Start. Logujesz się swoim kontem eDokumentów.</p>
      <p v-if="installed" role="status">Aplikacja jest otwarta w osobnym oknie.</p>
      <button v-else-if="installAvailable" class="primary" :disabled="busy" @click="run(installPwa)"><Download :size="18" /> Zainstaluj aplikację</button>
      <p v-else class="muted">W Chrome lub Edge otwórz menu przeglądarki i wybierz instalację aplikacji. Na Androidzie opcja może nazywać się „Dodaj do ekranu głównego”. Jeśli aplikacja jest już zainstalowana, otwórz ją z jej ikony.</p>
    </section>
    <section class="pwa-block"><h3><Bell :size="19" /> Powiadomienia na tym urządzeniu</h3>
      <p>Alerty o nowych wiadomościach, zadaniach oraz terminach za 24 godziny i za godzinę. Treść dokumentów i wiadomości nie pojawia się na ekranie blokady.</p>
      <p v-if="!supported" role="status">Otwórz aplikację przez HTTPS w aktualnym Chrome lub Edge. Lokalnie możesz testować na localhost.</p>
      <p v-else-if="config && !config.configured" role="status">Instalacja PWA jest dostępna. Powiadomienia wymagają jeszcze skonfigurowania Web Push przez administratora serwera.</p>
      <p v-if="permission === 'denied'" role="status">Powiadomienia są zablokowane. Zmień zgodę w ustawieniach witryny w przeglądarce.</p>
      <label>Nazwa urządzenia<input v-model="name" maxlength="80" :disabled="busy" /></label>
      <div class="pwa-preferences"><label><input v-model="preferences.messages" type="checkbox" :disabled="busy" /> Nowe wiadomości</label><label><input v-model="preferences.tasks" type="checkbox" :disabled="busy" /> Nowe zadania</label><label><input v-model="preferences.reminders" type="checkbox" :disabled="busy" /> Przypomnienia o terminach</label></div>
      <div class="pwa-actions"><button class="primary" :disabled="busy || !supported || !config?.configured || !name.trim()" @click="enable">{{ current ? 'Połącz ponownie' : 'Włącz powiadomienia' }}</button><button v-if="current" :disabled="busy || !name.trim()" @click="save">Zapisz ustawienia</button><button v-if="current" :disabled="busy || !config?.configured" @click="test">Wyślij test</button></div>
      <p class="muted">Wymagane są internet i zgoda systemowa. Tryb „Nie przeszkadzać” oraz oszczędzanie energii mogą opóźniać alerty. Wylogowanie lub wygaśnięcie sesji wyłącza wysyłkę — po ponownym logowaniu połącz urządzenie ponownie.</p>
    </section>
    <section class="pwa-block"><h3>Twoje urządzenia</h3><p v-if="!devices.length" class="muted">Nie masz jeszcze urządzeń z włączonymi powiadomieniami.</p>
      <ul v-else class="pwa-devices"><li v-for="device in devices" :key="device.id"><span>{{ device.name }} <small v-if="device.id === currentId" class="muted">(to urządzenie)</small></span><button :disabled="busy" :aria-label="'Wyłącz powiadomienia: ' + device.name" @click="remove(device)"><Trash2 :size="17" /> Wyłącz</button></li></ul>
    </section>
  </section>
</template>

<style scoped>
.pwa-settings{width:min(680px,calc(100vw - 24px));max-height:90dvh;overflow:auto;padding:24px}.pwa-settings>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.pwa-settings h2,.pwa-settings h3{display:flex;align-items:center;gap:9px}.pwa-settings h2{margin:8px 0 18px}.pwa-settings h3{font-size:16px;margin:0 0 10px}.pwa-settings p{font-size:14px;line-height:1.6}.pwa-block{padding:20px 0;border-top:1px solid var(--border)}.pwa-block>label{display:grid;gap:8px;font-size:14px}.pwa-preferences{display:grid;gap:12px;margin:18px 0}.pwa-preferences label{display:flex;flex-direction:row;justify-content:flex-start;align-items:center;text-align:left;gap:10px;font-size:14px}.pwa-preferences input{width:18px;height:18px;accent-color:var(--accent)}.pwa-actions{display:flex;flex-wrap:wrap;gap:10px}.pwa-devices{list-style:none;padding:0;display:grid;gap:12px}.pwa-devices li{display:flex;align-items:center;justify-content:space-between;gap:12px}.pwa-devices li span{overflow-wrap:anywhere}.pwa-error{color:var(--danger,#b42318)}@media(max-width:600px){.pwa-settings{padding:18px}.pwa-settings h2{font-size:18px}.pwa-actions>button{flex:1 1 100%}}
</style>
