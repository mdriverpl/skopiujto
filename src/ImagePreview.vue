<script setup>
import { computed, ref, watch } from 'vue'
import { Image as ImageIcon } from 'lucide-vue-next'

const props = defineProps({ documentId: { type: String, required: true }, version: [Number, String], name: String })
const failed = ref(false)
const source = computed(() => `/api/documents/${encodeURIComponent(props.documentId)}/preview?v=${encodeURIComponent(props.version ?? '')}`)
watch(source, () => { failed.value = false })
</script>

<template>
  <span class="file-thumbnail">
    <img v-if="!failed" :src="source" :alt="`Podgląd ${name || 'obrazu'}`" loading="lazy" decoding="async" @error="failed = true" />
    <span v-else class="thumbnail-unavailable"><ImageIcon :size="30" aria-hidden="true" /><small>Podgląd niedostępny</small></span>
  </span>
</template>
