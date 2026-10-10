<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Palette, Sun, Moon, Heart, Rainbow } from 'lucide-vue-next'
import { themes, savedTheme, applyTheme } from './theme.js'

const current = ref(savedTheme())
const open = ref(false)
const picker = ref(null)
const icons = { normal: Sun, dark: Moon, sweet: Heart, colorful: Rainbow }
function choose(id) { current.value = applyTheme(id); open.value = false }
function closeOutside(event) { if (!picker.value?.contains(event.target)) open.value = false }
function sync(event) { if (event.key === 'edokumenty-theme') current.value = applyTheme(savedTheme()) }
onMounted(() => { document.addEventListener('pointerdown', closeOutside); window.addEventListener('storage', sync) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', closeOutside); window.removeEventListener('storage', sync) })
</script>

<template>
  <div ref="picker" class="theme-picker" @keydown.esc.stop="open = false">
    <button class="icon-button theme-toggle" aria-label="Wybierz motyw" title="Wybierz motyw" :aria-expanded="open" aria-controls="theme-options" @click="open = !open"><Palette :size="20" /></button>
    <div v-if="open" id="theme-options" class="theme-options" role="group" aria-label="Motyw aplikacji">
      <button v-for="theme in themes" :key="theme.id" :aria-label="theme.label" :title="theme.label" :aria-pressed="current === theme.id" @click="choose(theme.id)"><component :is="icons[theme.id]" :size="19" /></button>
    </div>
  </div>
</template>

<style scoped>
.theme-picker { position: relative; }
.theme-toggle { color: var(--theme-accent, var(--accent)); }
.theme-options { position: absolute; top: calc(100% + 10px); right: 0; z-index: 40; display: flex; gap: 3px; padding: 8px; border: 1px solid var(--theme-border, var(--border)); border-radius: 14px; background: var(--theme-surface, white); box-shadow: 0 10px 30px #0002; }
.theme-heading { display: block; padding: 8px 10px; font-size: 11px; color: var(--theme-muted, var(--secondary)); }
.theme-options button { border: none; padding: 10px; }
.theme-options button span { flex: 1; text-align: left; }
.theme-options button[aria-pressed='true'] { color: var(--theme-accent, var(--accent)); background: var(--theme-accent-soft, var(--accent-soft)); }
</style>
