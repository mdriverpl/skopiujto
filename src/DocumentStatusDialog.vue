<script setup>
import { ref } from 'vue'
import { X, Save } from 'lucide-vue-next'

const props = defineProps({ document: Object, api: Function })
const emit = defineEmits(['close', 'saved'])
const status = ref(props.document.status), busy = ref(false), error = ref('')
const statuses = ['Do podpisania', 'Do modyfikacji', 'Do akceptacji', 'W toku', 'Szkic', 'Gotowy', 'Archiwum']
async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    await props.api(`/documents/${props.document.id}/status`, 'PATCH', { status: status.value, version: props.document.version })
    emit('saved')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="modal-backdrop">
    <section class="panel status-dialog" role="dialog" aria-modal="true" aria-labelledby="status-dialog-title">
      <div class="editor-heading"><h2 id="status-dialog-title">Status dokumentu</h2><button class="icon-button" :disabled="busy" aria-label="Zamknij zmianę statusu" @click="emit('close')"><X :size="19" /></button></div>
      <p class="document-name">{{ document.title }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <form @submit.prevent="save">
        <label>Status<select v-model="status" :disabled="busy"><option v-for="item in statuses" :key="item">{{ item }}</option></select></label>
        <p class="muted">Dokumenty wymagające działania trafiają do „Aktywnych dokumentów”. „Gotowy” kończy pracę nad dokumentem; oczekujące akceptacje i otwarte terminy pozostają na liście. „Archiwum” usuwa dokument z listy aktywnych.</p>
        <div class="editor-actions"><button type="button" :disabled="busy" @click="emit('close')">Anuluj</button><button class="primary" :disabled="busy" type="submit"><Save :size="16" /> {{ busy ? 'Zapisywanie…' : 'Zapisz status' }}</button></div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.status-dialog { width: 460px; max-width: 100%; max-height: 90vh; overflow-y: auto; padding: 24px; }
.document-name { font-size: 13px; color: var(--secondary); overflow-wrap: anywhere; margin: 0 0 20px; }
.muted { font-size: 12px; margin: 0; }
</style>
