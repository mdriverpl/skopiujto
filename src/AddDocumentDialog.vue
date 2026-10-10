<script setup>
import { computed, ref } from 'vue'
import { FilePlus2, BookOpen, X, ArrowRight, FileText, Sparkles } from 'lucide-vue-next'
import AiPrompt from './AiPrompt.vue'

const props = defineProps({ templates: { type: Array, default: () => [] }, folderName: String, folderId: { type: String, default: null }, api: Function })
const emit = defineEmits(['close', 'choose'])
const source = ref('blank')
const generating = ref(false)
const templateId = ref('')
const selected = computed(() => props.templates.find(item => item.id === templateId.value))
function proceed() {
  if (generating.value || source.value === 'ai' || (source.value === 'template' && !selected.value)) return
  const item = source.value === 'template' ? selected.value : null
  emit('choose', {
    title: item?.title || '', category: item?.category || 'Inne', status: 'Szkic',
    content: item?.content || '', rich_content: item?.rich_content ? JSON.parse(JSON.stringify(item.rich_content)) : null
  })
}
</script>

<template>
  <div class="modal-backdrop" @keydown.esc="!generating && emit('close')">
    <section class="panel add-document-dialog" role="dialog" aria-modal="true" aria-labelledby="add-document-title">
      <header><span class="dialog-mark"><FilePlus2 :size="22" /></span><div><h2 id="add-document-title">Dodaj plik</h2><p>Nowy dokument w: {{ folderName || 'Mój dysk' }}</p></div><button class="icon-button" :disabled="generating" aria-label="Zamknij" @click="emit('close')"><X :size="20" /></button></header>
      <div class="dialog-body">
        <div class="source-options" role="group" aria-label="Sposób tworzenia dokumentu">
          <button :disabled="generating" :aria-pressed="source === 'blank'" @click="source = 'blank'"><FilePlus2 :size="24" /><strong>Nowy pusty</strong><span>Zacznij od czystej kartki.</span></button>
          <button :disabled="generating" :aria-pressed="source === 'template'" @click="source = 'template'"><BookOpen :size="24" /><strong>Z szablonu</strong><span>Wybierz gotowy wzór.</span></button>
          <button :disabled="generating" :aria-pressed="source === 'ai'" @click="source = 'ai'"><Sparkles :size="24" /><strong>Z AI</strong><span>Opisz, co stworzyć.</span></button>
        </div>
        <div v-if="source === 'template'" class="template-choice">
          <label for="new-document-template">Szablon do wyboru</label>
          <select id="new-document-template" v-model="templateId" autofocus><option disabled value="">Wybierz szablon…</option><option v-for="item in templates" :key="item.id" :value="item.id">{{ item.title }} · {{ item.category }}</option></select>
          <div v-if="selected" class="template-summary"><FileText :size="19" /><div><strong>{{ selected.title }}</strong><p>{{ selected.description || 'Wzór dokumentu gotowy do dostosowania.' }}</p><pre>{{ selected.content.slice(0, 220) }}{{ selected.content.length > 220 ? '…' : '' }}</pre></div></div>
          <p v-if="!templates.length" class="hint">Nie masz jeszcze dostępnych szablonów. Możesz utworzyć pusty dokument.</p>
        </div>
        <AiPrompt v-if="source === 'ai'" :api="api" :folder-id="folderId" @busy="generating = $event" @generated="emit('choose', $event)" />
        <p v-else class="hint">W edytorze nadasz nazwę i uzupełnisz treść. Dokument pojawi się na dysku po zapisaniu.</p>
      </div>
      <footer><button :disabled="generating" @click="emit('close')">Anuluj</button><button v-if="source !== 'ai'" class="primary" :disabled="source === 'template' && !selected" @click="proceed">Otwórz edytor <ArrowRight :size="16" /></button></footer>
    </section>
  </div>
</template>

<style scoped>
.add-document-dialog { width: 640px; max-width: 100%; max-height: 92vh; overflow-y: auto; border-radius: 18px; }
header { display: flex; align-items: center; gap: 13px; padding: 22px 24px; border-bottom: 1px solid var(--border); }
.dialog-mark { display: flex; padding: 11px; border-radius: 11px; background: var(--accent-soft); color: var(--accent); }
header > div { flex: 1; min-width: 0; }
h2 { font-size: 18px; margin: 0; }
header p { font-size: 12px; margin: 6px 0 0; color: var(--muted); overflow-wrap: anywhere; }
.dialog-body { padding: 24px; }
.source-options { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.source-options button { display: flex; flex-direction: column; align-items: flex-start; padding: 20px; gap: 12px; background: var(--theme-surface-soft, #fbfbfd); border: 1px solid var(--border); border-radius: 12px; text-align: left; color: var(--muted); }
.source-options button[aria-pressed='true'] { border-color: var(--theme-accent, #b5a7ee); background: var(--accent-soft); color: var(--accent); box-shadow: 0 0 0 1px var(--theme-accent, #b5a7ee); }
.source-options strong { font-size: 14px; color: var(--theme-text, #34384e); }
.source-options span { font-size: 12px; }
.template-choice { display: flex; flex-direction: column; gap: 10px; margin-top: 22px; }
.template-choice label { color: var(--secondary); font-size: 12px; }
.template-choice select { width: 100%; font-size: 13px; }
.template-summary { display: flex; align-items: flex-start; gap: 12px; background: var(--surface-soft); border-radius: 10px; padding: 16px; color: var(--accent); }
.template-summary > svg { flex-shrink: 0; }
.template-summary > div { min-width: 0; }
.template-summary strong { font-size: 13px; color: var(--secondary); }
.template-summary p { color: var(--muted); font-size: 12px; line-height: 1.6; margin: 6px 0 0; }
.template-summary pre { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--theme-muted, #969bad); font: 11px/1.7 Inter, sans-serif; margin: 12px 0 0; }
.hint { font-size: 12px; line-height: 1.7; color: var(--muted); margin: 18px 0 0; }
footer { display: flex; justify-content: flex-end; gap: 10px; padding: 18px 24px; border-top: 1px solid var(--border); }
footer button { font-size: 12px; }
@media (max-width: 480px) { header, .dialog-body, footer { padding: 18px; } .source-options { grid-template-columns: 1fr; } .source-options button { gap: 8px; padding: 16px; } }
</style>
