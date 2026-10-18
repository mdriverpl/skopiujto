<script setup>
import { onMounted, ref } from 'vue'
import { Save, CheckCircle2 } from 'lucide-vue-next'
const props = defineProps({ api: Function, initial: Object })
const emit = defineEmits(['saved', 'close'])
const busy = ref(false), loading = ref(false), loaded = ref(!!props.initial), error = ref(''), notice = ref('')
const connectionForm = (value = {}) => ({ enabled: false, address: '', system_name: '', version: 0, ...value, certificate: '', private_key: '', key_password: '' })
const form = ref(connectionForm(props.initial))
async function load() {
  if (loading.value) return
  loading.value = true; error.value = ''
  try {
    form.value = connectionForm(await props.api('/edeliveries/connection'))
    loaded.value = true
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}
async function readFile(event, field) {
  const file = event.target.files?.[0]
  if (!file) return
  error.value = ''
  if (file.size > 32000) { error.value = 'Plik PEM może mieć maksymalnie 32 KB.'; return }
  try {
    const value = await file.text()
    if (!value.includes('-----BEGIN ')) { error.value = 'Wybierz plik w tekstowym formacie PEM.'; return }
    form.value[field] = value
  } catch { error.value = 'Nie udało się odczytać pliku.' }
  event.target.value = ''
}
async function save(test = false) {
  if (busy.value || loading.value || !loaded.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const value = form.value
    const body = { enabled: value.enabled, address: value.address, system_name: value.system_name, version: value.version,
      certificate: value.certificate || null, private_key: value.private_key || null, key_password: value.private_key ? value.key_password : (value.key_password || null) }
    const saved = await props.api('/edeliveries/connection', 'PUT', body)
    form.value = connectionForm(saved)
    emit('saved', saved)
    notice.value = 'Konfiguracja została zapisana.'
    if (test) notice.value = (await props.api('/edeliveries/connection/test', 'POST')).message
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function disconnect() {
  if (busy.value || loading.value || !loaded.value || !window.confirm('Usunąć konfigurację połączenia i zapisane dane dostępowe? Wpisy w rejestrze pozostaną.')) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await props.api('/edeliveries/connection', 'DELETE')
    form.value = connectionForm()
    emit('saved', { enabled: false, address: '', system_name: '', version: 0 })
    notice.value = 'Skrzynka została odłączona. Wpisy w rejestrze pozostają dostępne.'
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(() => { if (!props.initial) return load() })
</script>

<template>
  <section class="connection-page" aria-labelledby="connection-title" :aria-busy="loading">
    <Teleport to="#workspace-title"><div><h1 id="connection-title">Ustawienia eDoręczeń</h1><p class="intro">Konfiguracja połączenia z Twoją skrzynką eDoręczeń.</p></div></Teleport>
    <div class="panel connection-panel">
    <p class="intro">Poczta Polska · środowisko produkcyjne · UA API v3. Wpisz dane systemu zewnętrznego upoważnionego w skrzynce. Dane są zapisane tylko na Twoim koncie.</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="success" role="status">{{ notice }}</p>
      <p v-if="loading" class="intro" role="status">Wczytywanie ustawień eDoręczeń…</p>
      <button v-if="!loaded && !loading" type="button" @click="load">Spróbuj ponownie</button>
    <form v-if="loaded" @submit.prevent="save()">
      <label class="check-label"><input v-model="form.enabled" type="checkbox" :disabled="busy" /> Włącz połączenie ze skrzynką</label>
      <label>Adres do eDoręczeń (ADE)<input v-model="form.address" maxlength="100" placeholder="AE:PL-…" :required="form.enabled" :disabled="busy" /></label>
      <label>Nazwa systemu zewnętrznego<input v-model="form.system_name" maxlength="100" placeholder="Dokładna nazwa zarejestrowana w skrzynce" :required="form.enabled" :disabled="busy" /></label>
      <label>Certyfikat X.509 (PEM)<input type="file" accept=".pem,.crt,.cer" :disabled="busy" @change="readFile($event, 'certificate')" /><textarea v-model="form.certificate" rows="3" maxlength="32000" :disabled="busy" autocomplete="off" placeholder="-----BEGIN CERTIFICATE-----" /></label><p class="field-help">{{ form.has_certificate ? 'Certyfikat zapisany. Puste pole zachowuje dotychczasowy certyfikat.' : 'Wczytaj certyfikat PEM powiązany z systemem zewnętrznym.' }}</p>
      <label>Klucz prywatny (PEM)<input type="file" accept=".pem,.key" :disabled="busy" @change="readFile($event, 'private_key')" /><textarea v-model="form.private_key" rows="3" maxlength="32000" :disabled="busy" autocomplete="off" spellcheck="false" placeholder="-----BEGIN PRIVATE KEY-----" /></label><p class="field-help">{{ form.has_private_key ? 'Klucz zapisany w postaci zaszyfrowanej. Puste pole zachowuje dotychczasowy klucz.' : 'Obsługiwane są pliki RSA (minimum 2048 bitów) lub EC P-256/P-384/P-521.' }} Klucz z urządzenia lub usługi podpisującej bez eksportu PEM wymaga osobnego adaptera.</p>
      <label>Hasło klucza prywatnego (jeśli jest zaszyfrowany)<input v-model="form.key_password" type="password" maxlength="1000" :disabled="busy" autocomplete="new-password" /></label>
      <p class="field-help">Dane dostępowe są szyfrowane kluczem EDOCUMENTS_MAIL_SETTINGS_KEY ustawionym na serwerze. Sam zapis nie potwierdza upoważnienia systemu przez operatora.</p>
      <footer><button type="button" :disabled="busy" @click="emit('close')">Przejdź do eDoręczeń</button><button v-if="form.version" type="button" class="disconnect" :disabled="busy" @click="disconnect">Odłącz skrzynkę</button><button type="button" :disabled="busy || !form.enabled" @click="save(true)"><CheckCircle2 :size="17" /> Zapisz i sprawdź</button><button class="primary" :disabled="busy"><Save :size="17" /> {{ busy ? 'Proszę czekać…' : 'Zapisz konfigurację' }}</button></footer>
    </form>
    </div>
  </section>
</template>

<style scoped>
.connection-page { width:100%; max-width:1000px; }
.connection-panel { padding:28px; display:grid; gap:18px; }
h1 { margin:0 0 8px; font-size:24px; }
.intro,.field-help { color:var(--muted); font-size:12px; line-height:1.7; margin:0; }
.field-help { margin:-8px 0 0; }
textarea { font-family:Consolas,monospace; font-size:12px; }
footer { display:flex; flex-wrap:wrap; justify-content:flex-start; gap:10px; }
footer button { font-size:12px; }
.disconnect { color:var(--danger); }
@media(max-width:600px) { .connection-panel { padding:18px; } }
</style>
