<script setup>
import { computed } from 'vue'
import { BookOpen, ArrowRight } from 'lucide-vue-next'
import { getHelpTopic } from './helpContent.js'
const props = defineProps({ view: String })
const emit = defineEmits(['open'])
const topic = computed(() => getHelpTopic(props.view))
</script>

<template>
  <details class="module-help">
    <summary><BookOpen :size="17" aria-hidden="true" /><span><strong>{{ topic.title }} — opis i pomoc</strong><small>{{ topic.description }}</small></span></summary>
    <div class="module-help-body"><ol><li v-for="step in topic.steps" :key="step">{{ step }}</li></ol><button @click="emit('open', topic.id)">Pełna instrukcja <ArrowRight :size="16" /></button></div>
  </details>
</template>

<style scoped>
.module-help { margin:0 0 20px; border:1px solid var(--border); background:var(--surface-soft); border-radius:12px; }
summary { display:flex; align-items:flex-start; gap:10px; padding:12px 14px; cursor:pointer; color:var(--secondary); }
summary svg { flex-shrink:0; margin-top:2px; color:var(--accent); } summary strong { font-size:12px; font-weight:600; } summary small { display:block; font-size:11px; line-height:1.6; color:var(--muted); margin-top:3px; }
summary:focus-visible { outline:3px solid var(--focus-ring); outline-offset:2px; border-radius:12px; }
.module-help-body { padding:0 18px 16px; } ol { padding-left:20px; margin:0 0 14px; font-size:12px; line-height:1.8; color:var(--secondary); } li + li { margin-top:6px; } button { font-size:12px; padding:8px 12px; }
</style>
