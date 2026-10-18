<script setup>
import { nextTick, ref } from 'vue'
import { ChevronDown, Check } from 'lucide-vue-next'
const props = defineProps({ status: String, label: String, title: String, options: Array, busy: Boolean })
const emit = defineEmits(['change'])
const popup = ref(null), expanded = ref(false), position = ref({})
async function toggle(event) {
  if (props.busy) return
  if (expanded.value) { popup.value.hidePopover(); return }
  const rect = event.currentTarget.getBoundingClientRect()
  const width = Math.min(200, window.innerWidth - 16), height = props.options.length * 38 + 16
  position.value = { left: `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`,
    top: `${rect.bottom + height + 8 > window.innerHeight ? Math.max(8, rect.top - height - 6) : rect.bottom + 6}px`, width: `${width}px` }
  await nextTick()
  popup.value?.showPopover()
  popup.value?.querySelector('button')?.focus()
}
function choose(status) {
  popup.value.hidePopover()
  if (!props.busy && status !== props.status) emit('change', status)
}
function navigate(event) {
  const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End']
  if (!keys.includes(event.key)) return
  event.preventDefault()
  const items = [...popup.value.querySelectorAll('button')]
  const current = items.indexOf(document.activeElement)
  const index = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
    : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
  items[index]?.focus()
}
</script>

<template>
  <span class="task-status-menu">
    <button type="button" class="task-status-trigger" :class="status" :disabled="busy" aria-haspopup="menu" :aria-expanded="expanded" :aria-label="`Status zadania: ${title} — ${label}`" title="Zmień status zadania" @click.stop="toggle">{{ label }}<ChevronDown :size="12" aria-hidden="true" /></button>
    <div ref="popup" popover="auto" role="menu" class="task-status-popup" aria-label="Zmień status zadania" :style="position" @toggle="expanded = $event.newState === 'open'" @keydown="navigate" @click.stop>
      <button v-for="option in options" :key="option.value" type="button" role="menuitemradio" :aria-checked="option.value === status" :disabled="busy" @click="choose(option.value)">{{ option.label }}<Check v-if="option.value === status" :size="15" aria-hidden="true" /></button>
    </div>
  </span>
</template>

<style scoped>
.task-status-menu { display:inline-flex; max-width:100%; }
.task-status-trigger { display:inline-flex; align-items:center; gap:5px; padding:5px 8px; border:0; border-radius:7px; font-size:var(--task-status-font-size,11px); color:var(--muted); background:var(--surface-soft); white-space:nowrap; }
.task-status-trigger.todo,.task-status-trigger.waiting { color:var(--warning); background:var(--warning-soft); }.task-status-trigger.in_progress { color:var(--accent); background:var(--accent-soft); }.task-status-trigger.done,.task-status-trigger.accepted { color:var(--success); background:var(--success-soft); }
.task-status-popup { position:fixed; inset:auto; margin:0; padding:7px; box-sizing:border-box; border:1px solid var(--border); border-radius:11px; background:var(--surface); color:var(--text); box-shadow:0 12px 35px #14213b26; }
.task-status-popup button { display:flex; justify-content:space-between; align-items:center; gap:12px; width:100%; min-height:38px; padding:9px 11px; border:0; border-radius:7px; background:transparent; text-align:left; font-size:12px; }
.task-status-popup button:hover,.task-status-popup button:focus-visible { background:var(--accent-soft); color:var(--accent); }.task-status-popup button[aria-checked="true"] { color:var(--accent); font-weight:600; }
</style>
