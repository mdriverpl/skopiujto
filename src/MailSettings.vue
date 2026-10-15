<script setup>
import { onMounted, ref } from 'vue'
import { X, Save, Server, Mail, CheckCircle2, Eye, EyeOff } from 'lucide-vue-next'
const props = defineProps({ api: Function, initial: Object })
const emit = defineEmits(['saved', 'close'])
const dialog = ref(null), busy = ref(false), error = ref(''), notice = ref(''), visible = ref({ smtp: false, imap: false })
const transport = (port, value = {}) => ({ enabled: false, host: '', port, security: 'ssl', username: '', ...value, password: '', clear_password: false })
const initial = props.initial?.account || {}
const form = ref({ email: initial.email || '', sender_name: initial.sender_name || '', version: initial.version || 0,
  smtp: transport(465, initial.smtp), imap: transport(993, initial.imap) })
async function persist() {
  const body = { email: form.value.email, sender_name: form.value.sender_name, version: form.value.version }
  for (const name of ['smtp', 'imap']) {
    const { enabled, host, port, security, username, password, clear_password } = form.value[name]
    body[name] = { enabled, host, port, security, username, password: password || null, clear_password }
  }
  const saved = await props.api('/client-mail/settings', 'PUT', body)
  form.value = { ...saved.account, smtp: transport(465, saved.account.smtp), imap: transport(993, saved.account.imap) }
  emit('saved', saved)
}
async function save(test = null) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await persist()
    notice.value = 'Ustawienia poczty zostały zapisane.'
    if (test) {
      const result = await props.api(`/client-mail/settings/test/${test}`, 'POST')
      notice.value = result.message
    }
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
function securityChanged(name) {
  form.value[name].port = name === 'smtp' ? (form.value[name].security === 'ssl' ? 465 : 587) : (form.value[name].security === 'ssl' ? 993 : 143)
}
function close() { if (!busy.value) { form.value.smtp.password = ''; form.value.imap.password = ''; emit('close') } }
onMounted(() => dialog.value.showModal())
</script>

<template>
  <dialog ref="dialog" class="mail-settings-dialog" aria-labelledby="mail-settings-title" @cancel.prevent="close">
    <form @submit.prevent="save()">
      <header><div><span class="settings-eyebrow">Twoje konto</span><h2 id="mail-settings-title"><Mail :size="22" /> Ustawienia poczty</h2></div><button type="button" class="settings-icon" :disabled="busy" aria-label="Zamknij ustawienia" @click="close" title="Zamknij ustawienia"><X :size="20" /></button></header>
      <p class="settings-intro">Wpisz dane otrzymane od dostawcy poczty. Ustawienia dotyczą tylko Twojego konta.</p>
      <p v-if="error" class="settings-error" role="alert">{{ error }}</p><p v-if="notice" class="settings-success" role="status"><CheckCircle2 :size="17" /> {{ notice }}</p>
      <fieldset :disabled="busy" class="account-fields"><legend>Dane nadawcy</legend><label>Adres e-mail<input v-model="form.email" type="email" maxlength="254" autocomplete="email" placeholder="jan@firma.pl" :required="form.smtp.enabled || form.imap.enabled" /></label><label>Nazwa nadawcy<input v-model="form.sender_name" maxlength="150" autocomplete="name" placeholder="Jan Kowalski" /></label></fieldset>
      <div class="server-grid">
        <fieldset v-for="name in ['smtp', 'imap']" :key="name" :disabled="busy" class="server-fields"><legend><Server :size="17" /> {{ name === 'smtp' ? 'Wysyłanie — SMTP' : 'Odbieranie — IMAP' }}</legend>
          <label class="checkbox-label"><input v-model="form[name].enabled" type="checkbox" /> {{ name === 'smtp' ? 'Używaj własnego serwera SMTP' : 'Zapisz konfigurację IMAP' }}</label>
          <label>Serwer {{ name.toUpperCase() }}<input v-model="form[name].host" maxlength="253" :required="form[name].enabled" :placeholder="`${name}.firma.pl`" autocomplete="off" autocapitalize="none" spellcheck="false" /></label>
          <div class="port-security"><label>Port<input v-model.number="form[name].port" type="number" min="1" max="65535" required /></label><label>Zabezpieczenia<select v-model="form[name].security" @change="securityChanged(name)"><option value="ssl">SSL / TLS</option><option value="starttls">STARTTLS</option></select></label></div>
          <label>Login<input v-model="form[name].username" maxlength="254" :required="name === 'imap' && form[name].enabled" :autocomplete="name === 'smtp' ? 'section-smtp username' : 'section-imap username'" placeholder="Najczęściej pełny adres e-mail" autocapitalize="none" spellcheck="false" /></label>
          <label>Hasło lub hasło aplikacji<span class="password-field"><input v-model="form[name].password" :type="visible[name] ? 'text' : 'password'" maxlength="1000" :autocomplete="name === 'smtp' ? 'section-smtp new-password' : 'section-imap new-password'" :placeholder="form[name].has_password ? 'Zapisane — pozostaw puste, aby zachować' : 'Wpisz hasło'" /><button type="button" class="settings-icon" :aria-label="`${visible[name] ? 'Ukryj' : 'Pokaż'} hasło ${name.toUpperCase()}`" :aria-pressed="visible[name]" @click="visible[name] = !visible[name]" :title="`${visible[name] ? 'Ukryj' : 'Pokaż'} hasło ${name.toUpperCase()}`"><EyeOff v-if="visible[name]" :size="17" /><Eye v-else :size="17" /></button></span></label>
          <label v-if="form[name].has_password" class="checkbox-label"><input v-model="form[name].clear_password" type="checkbox" /> Usuń zapisane hasło {{ name.toUpperCase() }}</label>
          <p class="field-help">{{ name === 'smtp' ? 'Wysyłanie będzie korzystać z podanego adresu i serwera. Wyłączenie tej opcji blokuje wysyłanie z Poczty.' : 'Możesz zapisać dane i sprawdzić połączenie. Odświeżanie nad listą wiadomości pobiera pocztę z INBOX przez IMAP.' }}</p>
          <button type="button" class="connection-button" :disabled="!form[name].enabled" @click="save(name)">{{ busy ? 'Zapisywanie / sprawdzanie…' : `Zapisz i sprawdź ${name.toUpperCase()}` }}</button>
        </fieldset>
      </div>
      <p class="field-help">Hasła są szyfrowane na serwerze. Zapisane hasło nie jest ponownie wyświetlane. Test połączenia nie wysyła wiadomości.</p>
      <footer><button type="button" :disabled="busy" @click="close">Zamknij</button><button class="primary" :disabled="busy"><Save :size="17" /> {{ busy ? 'Zapisywanie…' : 'Zapisz ustawienia' }}</button></footer>
    </form>
  </dialog>
</template>

<style scoped>
.mail-settings-dialog { width:min(780px,calc(100vw - 28px)); max-height:90dvh; padding:28px; border:1px solid var(--border); border-radius:20px; background:var(--surface); color:var(--text); box-shadow:0 25px 80px #0003; }
.mail-settings-dialog::backdrop { background:#13213966; backdrop-filter:blur(5px); }
form { gap:18px; }header,footer { display:flex; align-items:center; justify-content:space-between; gap:15px; }h2 { display:flex; gap:10px; align-items:center; margin:7px 0 0; font-size:22px; }h2 svg { color:#086cff; }.settings-eyebrow { color:var(--muted); font-size:10px; text-transform:uppercase; letter-spacing:1.5px; }
.settings-intro { color:var(--secondary); font-size:12px; line-height:1.7; margin:0; }.settings-icon { border:0; background:transparent; padding:7px; flex-shrink:0; color:var(--secondary); }
fieldset { border:1px solid var(--border); border-radius:13px; padding:18px; margin:0; min-width:0; }legend { padding:0 7px; font-size:12px; font-weight:600; }legend svg { vertical-align:middle; margin-right:5px; color:#086cff; }
.account-fields,.server-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }.server-fields { display:flex; flex-direction:column; gap:14px; background:var(--surface-soft); }
label { font-size:12px; gap:7px; }input,select { font-size:12px; padding:10px; } .port-security { display:grid; grid-template-columns:90px 1fr; gap:12px; }.checkbox-label { flex-direction:row; align-items:center; gap:9px; font-size:11px; line-height:1.5; }.checkbox-label input { width:15px; height:15px; flex-shrink:0; accent-color:#086cff; }.password-field { display:flex; align-items:center; border:1px solid var(--border); background:var(--surface); border-radius:8px; }.password-field input { border:0; flex:1; width:0; }.field-help { font-size:10px; line-height:1.7; color:var(--muted); margin:0; }.connection-button { font-size:11px; padding:10px; margin-top:auto; color:#086cff; background:var(--surface); }.settings-error,.settings-success { padding:12px; border-radius:9px; margin:0; font-size:12px; line-height:1.6; }.settings-error { color:var(--theme-danger,#ba253b); background:color-mix(in srgb,#ff637d 10%,var(--surface)); }.settings-success { display:flex; align-items:center; gap:8px; background:var(--success-soft); color:var(--success); }footer { justify-content:flex-end; }footer button { font-size:12px; }
@media(max-width:600px) { .mail-settings-dialog { padding:20px; max-height:94dvh; }.account-fields,.server-grid { grid-template-columns:1fr; }.settings-intro { font-size:11px; }h2 { font-size:19px; } }
</style>
