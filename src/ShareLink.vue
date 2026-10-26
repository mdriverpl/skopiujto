<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Copy, Share2, X, Check } from 'lucide-vue-next'
const props = defineProps({ url: String, title: String, photo: Boolean })
const emit = defineEmits(['close'])
const dialog = ref(null), input = ref(null), copied = ref(false), error = ref('')
const nativeShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'
let trigger, previousOverflow
async function copy() {
  error.value = ''
  try { await navigator.clipboard.writeText(props.url); copied.value = true }
  catch { input.value?.focus(); input.value?.select(); error.value = 'Skopiuj zaznaczony adres z pola powyżej.' }
}
async function share() {
  try { await navigator.share({ title: props.title, url: props.url }) }
  catch (err) { if (err.name !== 'AbortError') error.value = 'Nie udało się udostępnić. Skopiuj link.' }
}
function keydown(event) {
  if (event.key === 'Escape') { event.preventDefault(); emit('close') }
  if (event.key !== 'Tab') return
  const elements = [...dialog.value.querySelectorAll('button,input')].filter(item => !item.disabled)
  if (event.shiftKey && document.activeElement === elements[0]) { event.preventDefault(); elements.at(-1)?.focus() }
  else if (!event.shiftKey && document.activeElement === elements.at(-1)) { event.preventDefault(); elements[0]?.focus() }
}
onMounted(async () => { trigger = document.activeElement; previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; await nextTick(); input.value?.focus(); input.value?.select() })
onBeforeUnmount(() => { document.body.style.overflow = previousOverflow; if (trigger?.isConnected) trigger.focus() })
</script>
<template>
  <Teleport to="body"><div class="share-link-backdrop" @click.self="emit('close')" @keydown.stop="keydown"><section ref="dialog" class="share-link-dialog" role="dialog" aria-modal="true" aria-labelledby="share-link-title"><header><h2 id="share-link-title"><Share2 :size="20" />Udostępnij {{ photo ? 'zdjęcie' : 'galerię' }}</h2><button aria-label="Zamknij udostępnianie linku" @click="emit('close')"><X :size="20" /></button></header><p>{{ title }}</p><label>Link do {{ photo ? 'zdjęcia' : 'galerii' }}<input ref="input" :value="url" readonly @focus="$event.target.select()" /></label><small>{{ photo ? 'Link otwiera wybrane zdjęcie. Odbiorca może przeglądać również pozostałą zawartość udostępnionej galerii.' : 'Odbiorca linku może przeglądać udostępnioną galerię bez logowania.' }} Obowiązuje termin ważności i dostęp ustawiony przez właściciela.</small><p v-if="error" class="share-link-error" role="alert">{{ error }}</p><footer><button @click="copy"><Check v-if="copied" :size="16" /><Copy v-else :size="16" />{{ copied ? 'Skopiowano' : 'Kopiuj link' }}</button><button v-if="nativeShare" @click="share"><Share2 :size="16" />Udostępnij przez…</button></footer></section></div></Teleport>
</template>
<style scoped>
.share-link-backdrop { position:fixed; inset:0; z-index:1300; background:#15213d88; backdrop-filter:blur(5px); display:grid; place-items:center; padding:20px; }.share-link-dialog { width:min(510px,100%); box-sizing:border-box; border-radius:16px; border:1px solid var(--border); background:var(--surface); color:var(--text); padding:24px; }header { display:flex; align-items:center; justify-content:space-between; gap:10px; }h2 { display:flex; gap:9px; align-items:center; font-size:19px; margin:0; }p { color:var(--muted); font-size:12px; overflow-wrap:anywhere; }label { display:grid; gap:8px; margin:20px 0 12px; font-size:12px; }input { width:100%; min-width:0; box-sizing:border-box; border:1px solid var(--border); border-radius:8px; padding:11px; background:var(--surface-soft); color:var(--text); font:inherit; font-size:12px; }small { display:block; color:var(--muted); line-height:1.8; font-size:11px; }footer { display:flex; gap:10px; flex-wrap:wrap; margin-top:20px; }button { display:inline-flex; align-items:center; justify-content:center; gap:7px; padding:10px 12px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--secondary); font:inherit; font-size:12px; cursor:pointer; }footer button:first-child { color:white; background:var(--accent); border-color:var(--accent); }button:focus-visible,input:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }.share-link-error { color:var(--theme-danger,#b92e48); }
</style>
