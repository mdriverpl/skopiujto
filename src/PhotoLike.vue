<script setup>
import { ref } from 'vue'
import { Heart } from 'lucide-vue-next'
const props = defineProps({ api: Function, token: String, photo: Object })
const emit = defineEmits(['updated'])
const busy = ref(false), error = ref('')
async function toggle() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const result = await props.api(`/public-shares/${encodeURIComponent(props.token)}/documents/${encodeURIComponent(props.photo.id)}/like`, 'PUT', { liked: !props.photo.liked })
    emit('updated', { id: props.photo.id, ...result })
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
</script>
<template>
  <div class="photo-like-control"><button class="photo-like-button" :class="{ liked: photo.liked }" :aria-pressed="!!photo.liked" :aria-label="`${photo.liked ? 'Cofnij polubienie' : 'Polub zdjęcie'}: ${photo.title}`" :title="photo.liked ? 'Cofnij polubienie' : 'Lubię to'" :disabled="busy" @click.stop="toggle"><Heart :size="18" :fill="photo.liked ? 'currentColor' : 'none'" /><span>{{ photo.likes_count || 0 }}</span></button><small v-if="error" class="photo-like-error" role="alert">{{ error }}</small></div>
</template>
<style scoped>
.photo-like-control { display:inline-flex; flex-direction:column; align-items:flex-start; min-width:0; }.photo-like-button { display:inline-flex; align-items:center; justify-content:center; gap:7px; min-height:36px; border:1px solid transparent; border-radius:8px; padding:7px 10px; background:transparent; color:var(--muted); font:inherit; font-size:12px; cursor:pointer; }.photo-like-button:hover { background:var(--surface-soft); border-color:var(--border); }.photo-like-button.liked { color:#dc2626; background:#fee2e2; }.photo-like-button:disabled { opacity:.55; cursor:wait; }.photo-like-button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }.photo-like-error { max-width:220px; color:var(--theme-danger,#ba253b); font-size:10px; line-height:1.5; overflow-wrap:anywhere; }
</style>
