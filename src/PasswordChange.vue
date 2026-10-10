<script setup>
import { ref } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({ api: { type: Function, required: true }, required: Boolean })
const emit = defineEmits(['saved', 'close'])
const currentPassword = ref('')
const newPassword = ref('')
const confirmation = ref('')
const busy = ref(false)
const error = ref('')
async function save() {
  if (busy.value) return
  error.value = ''
  if (newPassword.value !== confirmation.value) { error.value = 'Powtórzone hasło nie jest zgodne z nowym hasłem.'; return }
  if (newPassword.value === currentPassword.value) { error.value = 'Nowe hasło musi różnić się od obecnego.'; return }
  busy.value = true
  try {
    const account = await props.api('/me/password', 'POST', { current_password: currentPassword.value, new_password: newPassword.value })
    currentPassword.value = newPassword.value = confirmation.value = ''
    emit('saved', account)
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
</script>

<template>
  <section class="panel editor" role="dialog" aria-modal="true" aria-labelledby="password-title">
    <div class="editor-heading"><h2 id="password-title">{{ required ? 'Ustaw własne hasło' : 'Zmień hasło' }}</h2><button v-if="!required" class="icon-button" :disabled="busy" aria-label="Zamknij" @click="emit('close')"><X :size="21" /></button></div>
    <p class="muted">{{ required ? 'Korzystasz z hasła tymczasowego. Ustaw własne hasło, aby otworzyć dokumenty.' : 'Podaj obecne hasło i nowe hasło. Zmiana zakończy Twoje pozostałe sesje.' }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <form @submit.prevent="save">
      <label>{{ required ? 'Hasło tymczasowe' : 'Obecne hasło' }}<input v-model="currentPassword" type="password" required minlength="10" maxlength="200" autocomplete="current-password" :disabled="busy" /></label>
      <label>Nowe hasło<input v-model="newPassword" type="password" required minlength="10" maxlength="200" autocomplete="new-password" :disabled="busy" /></label>
      <label>Powtórz nowe hasło<input v-model="confirmation" type="password" required minlength="10" maxlength="200" autocomplete="new-password" :disabled="busy" /></label>
      <p class="muted">Hasło musi mieć co najmniej 10 znaków.</p>
      <div class="editor-actions"><button v-if="!required" type="button" :disabled="busy" @click="emit('close')">Anuluj</button><button class="primary" type="submit" :disabled="busy">{{ busy ? 'Zapisywanie…' : 'Zapisz hasło' }}</button></div>
    </form>
  </section>
</template>
