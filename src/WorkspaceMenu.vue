<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { House, Mail, ClipboardList, CalendarDays, StickyNote, Files, ClipboardCheck, HardDrive, FileText, BookOpen, Users, X } from 'lucide-vue-next'
import { defaultMenuOrder, normalizeMenuOrder, moveMenuItem } from './menuOrder.js'

const props = defineProps({ user: Object, api: Function, view: String, open: Boolean, tasksWaiting: Number, activeSurveys: Number })
const emit = defineEmits(['navigate', 'close', 'order-saved'])
const menu = ref(null), order = ref([...defaultMenuOrder]), dragged = ref(null), announcement = ref('')
let gesture = null, suppressClick = false
const saving = ref(false), saveError = ref('')
let disposed = false
const definitions = {
  start: { label: 'Start', icon: House }, ai: { label: 'Wiadomości', icon: Mail },
  mail: { label: 'Poczta Klienta', icon: Mail },
  edelivery: { label: 'eDor\u0119czenia', icon: Mail },
  tasks: { label: 'Zadania', icon: ClipboardList }, calendar: { label: 'Terminarz', icon: CalendarDays },
  notes: { label: 'Notatki', icon: StickyNote }, documents: { label: 'Dokumenty', icon: Files },
  surveys: { label: 'Ankiety', icon: ClipboardCheck }, drive: { label: 'Mój dysk', icon: HardDrive },
  templates: { label: 'Szablony', icon: FileText }, dictionaries: { label: 'Słowniki', icon: BookOpen },
  companies: { label: 'Katalog firm', icon: Users },
  help: { label: 'Pomoc', icon: BookOpen }, admin: { label: 'Użytkownicy i grupy', icon: Users }
}
const items = computed(() => order.value.filter(id => (id !== 'admin' || (props.user?.role === 'admin' && !props.user?.impersonation)) && (id !== 'companies' || props.user?.is_superadmin))
  .map(id => ({ id, ...definitions[id] })))
const active = id => props.view === id || (id === 'drive' && props.view === 'active')
async function saveOrder() {
  if (saving.value || !props.user?.id) return
  const accountId = props.user.id
  saving.value = true
  saveError.value = ''; announcement.value = ''
  try {
    const result = await props.api('/me/menu-order', 'PUT', { menu_order: [...order.value] })
    if (disposed || props.user?.id !== accountId) return
    emit('order-saved', result.menu_order)
    announcement.value = 'Kolejność menu została zapisana na Twoim koncie.'
    try { localStorage.removeItem(`edokumenty-menu-order:${accountId}`) } catch {}
  } catch (error) {
    if (!disposed && props.user?.id === accountId) saveError.value = 'Nie udało się zapisać kolejności menu. Spróbuj ponownie.'
  } finally {
    if (!disposed && props.user?.id === accountId) saving.value = false
  }
}
watch(() => props.user?.id, () => {
  cancelDrag()
  saving.value = false; saveError.value = ''; announcement.value = ''
  order.value = normalizeMenuOrder(props.user?.menu_order)
  // Transfer an existing browser preference once, when this account has no saved order yet.
  if (props.user?.id && !props.user.menu_order?.length) {
    try {
      const legacy = JSON.parse(localStorage.getItem(`edokumenty-menu-order:${props.user.id}`))
      if (Array.isArray(legacy) && legacy.length) { order.value = normalizeMenuOrder(legacy); saveOrder() }
    } catch {}
  }
}, { immediate: true })

function select(id, event) {
  if (suppressClick || event.ctrlKey) { suppressClick = false; return }
  emit('navigate', id)
  emit('close')
}
function pointerDown(id, event) {
  suppressClick = false
  if (saving.value || !event.ctrlKey || event.button !== 0 || event.pointerType !== 'mouse') return
  event.preventDefault()
  gesture = { id, pointerId: event.pointerId, x: event.clientX, y: event.clientY, original: [...order.value] }
  menu.value?.setPointerCapture(event.pointerId)
}
function inside(event) {
  const bounds = menu.value?.getBoundingClientRect()
  return bounds && event.clientX >= bounds.left && event.clientX <= bounds.right && event.clientY >= bounds.top && event.clientY <= bounds.bottom
}
function pointerMove(event) {
  if (!gesture || gesture.pointerId !== event.pointerId) return
  if (!dragged.value && Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) < 5) return
  dragged.value = gesture.id
  suppressClick = true
  event.preventDefault()
  if (!inside(event)) return
  for (const button of menu.value.querySelectorAll('[data-menu-id]')) {
    const bounds = button.getBoundingClientRect()
    if (event.clientY >= bounds.top && event.clientY <= bounds.bottom) {
      order.value = moveMenuItem(order.value, gesture.id, button.dataset.menuId, event.clientY > bounds.top + bounds.height / 2)
      break
    }
  }
}
function finishGesture() {
  const pointerId = gesture?.pointerId
  gesture = null
  dragged.value = null
  if (pointerId !== undefined && menu.value?.hasPointerCapture(pointerId)) menu.value.releasePointerCapture(pointerId)
}
function pointerUp(event) {
  if (!gesture || gesture.pointerId !== event.pointerId) return
  if (dragged.value && inside(event)) {
    saveOrder()
  } else order.value = gesture.original
  finishGesture()
}
function cancelDrag() {
  if (gesture) order.value = gesture.original
  finishGesture()
}
function keyMove(id, event) {
  if (event.key === 'Escape') { cancelDrag(); return }
  if (saving.value || !event.ctrlKey || !['ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const index = items.value.findIndex(item => item.id === id)
  const target = items.value[index + (event.key === 'ArrowUp' ? -1 : 1)]
  if (!target) return
  order.value = moveMenuItem(order.value, id, target.id, event.key === 'ArrowDown')
  saveOrder()
}
watch(() => props.open, () => cancelDrag())
onBeforeUnmount(() => { disposed = true; cancelDrag() })
</script>

<template>
  <nav ref="menu" id="workspace-menu" class="workspace-sidebar" :class="{ open, 'menu-reordering': dragged }" aria-label="Przestrzeń robocza" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="cancelDrag" @lostpointercapture="cancelDrag" @keydown.esc="cancelDrag">
    <div class="sidebar-heading"><span class="eyebrow">Menu</span><button class="icon-button sidebar-close" aria-label="Zamknij menu" @click="emit('close')"><X :size="20" /></button></div>
    <p class="menu-reorder-hint">Ctrl + przeciągnięcie zmienia kolejność</p>
    <p v-if="saving" class="menu-reorder-hint" role="status">Zapisywanie kolejności…</p>
    <div v-if="saveError" class="menu-save-error" role="alert"><p>{{ saveError }}</p><button @click="saveOrder">Spróbuj ponownie</button></div>
    <button v-for="item in items" :key="item.id" :data-menu-id="item.id" :class="{ active: active(item.id), 'menu-dragged': dragged === item.id }" :aria-current="active(item.id) ? 'page' : undefined" :title="`${item.label} — Ctrl + przeciągnięcie lub Ctrl + strzałki zmienia kolejność`" @pointerdown="pointerDown(item.id, $event)" @click="select(item.id, $event)" @keydown="keyMove(item.id, $event)">
      <component :is="item.icon" :size="18" /> {{ item.label }}<span v-if="item.id === 'tasks' && tasksWaiting">({{ tasksWaiting }})</span><span v-if="item.id === 'surveys'">({{ activeSurveys }})</span>
    </button>
    <span class="menu-announcement" role="status" aria-live="polite">{{ announcement }}</span>
  </nav>
</template>

<style scoped>
.menu-reorder-hint { font-size:10px; line-height:1.5; color:var(--muted); padding:0 14px; margin:-8px 0 8px; }
.menu-reordering { user-select:none; cursor:grabbing; }
.menu-reordering > button { cursor:grabbing; }
.workspace-sidebar > button.menu-dragged { opacity:.6; outline:2px dashed var(--accent); outline-offset:-2px; }
.menu-announcement { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
.menu-save-error { padding:0 14px; font-size:11px; color:var(--theme-danger, #a95353); }
.menu-save-error button { font-size:11px; padding:6px 9px; }
</style>
