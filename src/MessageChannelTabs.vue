<script setup>
import { Mail, MessageSquare, Users } from 'lucide-vue-next'
defineProps({ modelValue: String, disabled: Boolean })
defineEmits(['update:modelValue'])
</script>
<template>
  <div class="message-channel-tabs" role="group" aria-label="Sposób wysłania wiadomości"><button type="button" :disabled="disabled" :aria-pressed="modelValue === 'email'" @click="$emit('update:modelValue', 'email')"><Mail :size="17" />E-mail</button><button type="button" :disabled="disabled" :aria-pressed="modelValue === 'sms'" @click="$emit('update:modelValue', 'sms')"><MessageSquare :size="17" />SMS</button><button type="button" :disabled="disabled" :aria-pressed="modelValue === 'user'" @click="$emit('update:modelValue', 'user')"><Users :size="17" />Portal</button></div>
</template>
<style scoped>
.message-channel-tabs { display:flex; gap:4px; padding:4px; border:1px solid var(--border); border-radius:10px; background:var(--surface-soft); }.message-channel-tabs button { display:inline-flex; align-items:center; gap:7px; flex:1; justify-content:center; padding:8px 10px; border:1px solid transparent; border-radius:7px; color:var(--muted); background:transparent; font-size:12px; }.message-channel-tabs button[aria-pressed="true"] { color:var(--accent); background:var(--surface); border-color:var(--border); box-shadow:0 1px 3px #14213b08; }
</style>
