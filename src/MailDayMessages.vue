<script setup>
defineProps({ messages: Array, folders: Array, disabled: Boolean })
const emit = defineEmits(['open'])
const time = value => new Date(value).toLocaleTimeString('pl-PL', { timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit' })
</script>
<template>
  <div class="day-messages"><button v-for="message in messages" :key="message.id" :disabled="disabled" :title="`Otwórz wiadomość: ${message.subject || '(bez tematu)'}`" @click="emit('open', message.id)"><span class="day-message-heading"><strong>{{ message.subject || '(bez tematu)' }}</strong><time :datetime="message.created_at">{{ time(message.created_at) }}</time></span><span class="day-message-sender">{{ message.sender_name || message.sender_email }}<span v-if="message.sender_name && message.sender_email"> · {{ message.sender_email }}</span></span><span class="day-message-meta"><span>{{ folders.find(item => item.id === message.folder)?.label }}</span><span v-if="message.company">{{ message.company.name }}</span><span v-if="message.unread">Nieprzeczytana</span></span></button><p v-if="!messages.length">Brak wiadomości w tej grupie.</p></div>
</template>
<style scoped>
.day-messages { display:grid; gap:7px; padding:10px 0; }.day-messages > button { display:grid; justify-content:stretch; gap:6px; width:100%; min-width:0; text-align:left; padding:12px; background:var(--surface-soft); }.day-message-heading { display:flex; gap:10px; justify-content:space-between; align-items:baseline; }.day-message-heading strong { font-size:12px; overflow-wrap:anywhere; }.day-message-heading time { font-size:10px; color:var(--muted); flex-shrink:0; }.day-message-sender { font-size:11px; color:var(--secondary); overflow-wrap:anywhere; }.day-message-meta { display:flex; gap:6px; flex-wrap:wrap; font-size:10px; color:var(--secondary); }.day-message-meta > span { background:var(--surface); padding:3px 6px; border-radius:5px; }.day-messages > p { margin:4px 0; font-size:12px; color:var(--muted); }
</style>
