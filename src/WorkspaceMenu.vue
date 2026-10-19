<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { House, Mail, Sparkles, Inbox, Send, ShieldAlert, Trash2, Archive, ChevronDown, ClipboardList, CalendarDays, StickyNote, Files, ClipboardCheck, FileText, BookOpen, Users, Settings, X, GitBranch } from 'lucide-vue-next'
import { defaultMenuOrder, normalizeMenuOrder, moveMenuItem } from './menuOrder.js'

const props = defineProps({ user: Object, api: Function, view: String, open: Boolean, tasksWaiting: Number, activeSurveys: Number, mailFolder: String, dictionaryId: String, dictionaryRevision: Number })
const emit = defineEmits(['navigate', 'mail-folder', 'dictionary', 'close', 'order-saved'])
const mailExpanded = ref(false)
const expandedGroups = ref({ planning: false, documents: false, dictionaries: false, settings: false })
const dictionaryList = ref([]), dictionaryError = ref(''), dictionariesLoading = ref(false)
let dictionaryRequest = 0
async function loadDictionaries() {
  const request = ++dictionaryRequest
  dictionaryError.value = ''
  if (!props.user?.id) { dictionaryList.value = []; dictionariesLoading.value = false; return }
  dictionariesLoading.value = true
  try {
    const list = await props.api('/dictionaries')
    if (request === dictionaryRequest && !disposed) dictionaryList.value = list
  } catch {
    if (request === dictionaryRequest && !disposed) dictionaryError.value = 'Nie udało się wczytać słowników.'
  } finally {
    if (request === dictionaryRequest && !disposed) dictionariesLoading.value = false
  }
}
const groups = {
  mail: ['mail', 'edelivery'], planning: ['calendar', 'tasks', 'notes'],
  documents: ['documents', 'surveys', 'templates', 'active', 'drive'], dictionaries: ['dictionaries'], settings: ['admin', 'mail-settings', 'edelivery-settings', 'flows', 'pwa']
}
const children = {
  planning: [{ id: 'calendar', label: 'Terminarz', icon: CalendarDays }, { id: 'tasks', label: 'Zadania', icon: ClipboardList }, { id: 'notes', label: 'Notatki', icon: StickyNote }],
  documents: [{ id: 'documents', label: 'Dokumenty', icon: Files }, { id: 'surveys', label: 'Ankiety', icon: ClipboardCheck }, { id: 'templates', label: 'Szablony', icon: FileText }],
  settings: [{ id: 'pwa', label: 'Aplikacja i powiadomienia', icon: Settings }, { id: 'flows', label: 'Flow', icon: GitBranch }, { id: 'admin', label: 'Użytkownicy i grupy', icon: Users }, { id: 'mail-settings', label: 'Ustawienia poczty', icon: Mail }, { id: 'edelivery-settings', label: 'Ustawienia eDoręczeń', icon: Mail }]
}
const canManageUsers = computed(() => props.user?.role === 'admin' && !props.user?.impersonation)
const visibleChildren = id => children[id]?.filter(item => (item.id !== 'admin' || canManageUsers.value) && (item.id !== 'pwa' || !props.user?.impersonation)) || []
const isExpanded = id => id === 'mail' ? mailExpanded.value : expandedGroups.value[id]
const mailFolders = [
  { id: 'analysis', label: 'Analiza AI', icon: Sparkles },
  { id: 'inbox', label: 'Odebrana', icon: Inbox },
  { id: 'sent', label: 'Wysłane', icon: Send },
  { id: 'drafts', label: 'Robocze', icon: FileText },
  { id: 'spam', label: 'Spam', icon: ShieldAlert },
  { id: 'trash', label: 'Śmieci', icon: Trash2 },
  { id: 'archive', label: 'Archiwum', icon: Archive }
]
watch(() => props.view, view => {
  for (const [id, views] of Object.entries(groups)) {
    if (!views.includes(view)) continue
    if (id === 'mail') mailExpanded.value = true
    else expandedGroups.value[id] = true
  }
}, { immediate: true })
const menu = ref(null), order = ref([...defaultMenuOrder]), dragged = ref(null), announcement = ref('')
let gesture = null, suppressClick = false
const saving = ref(false), saveError = ref('')
let disposed = false
const definitions = {
  start: { label: 'Start', icon: House },
  mail: { label: 'Centrum wiadomości', icon: Mail },
  planning: { label: 'Planowanie', icon: CalendarDays },
  edelivery: { label: 'eDor\u0119czenia', icon: Mail },
  tasks: { label: 'Zadania', icon: ClipboardList }, calendar: { label: 'Terminarz', icon: CalendarDays },
  notes: { label: 'Notatki', icon: StickyNote }, documents: { label: 'Dokumenty', icon: Files },
  surveys: { label: 'Ankiety', icon: ClipboardCheck },
  templates: { label: 'Szablony', icon: FileText }, dictionaries: { label: 'Słowniki', icon: BookOpen },
  help: { label: 'Pomoc', icon: BookOpen }, settings: { label: 'Ustawienia', icon: Settings }
}
const items = computed(() => order.value.map(id => ({ id, ...definitions[id] })))
const active = id => groups[id]?.includes(props.view) || props.view === id
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
watch(() => [props.user?.id, props.dictionaryRevision], (value, previous) => {
  if (value[0] !== previous?.[0]) dictionaryList.value = []
  loadDictionaries()
}, { immediate: true })

function select(id, event) {
  if (suppressClick || event.ctrlKey) { suppressClick = false; return }
  if (groups[id]) {
    if (id === 'mail') mailExpanded.value = !mailExpanded.value
    else expandedGroups.value[id] = !expandedGroups.value[id]
    if (id === 'dictionaries' && expandedGroups.value[id] && !dictionariesLoading.value) loadDictionaries()
    return
  }
  emit('navigate', id)
  emit('close')
}
function selectChild(id, event) {
  if (suppressClick || event.ctrlKey) { suppressClick = false; return }
  emit('navigate', id)
  emit('close')
}
function selectDictionary(id, event) {
  if (suppressClick || event.ctrlKey) { suppressClick = false; return }
  emit('dictionary', id)
  emit('close')
}
function selectMailFolder(id, event) {
  if (suppressClick || event.ctrlKey) { suppressClick = false; return }
  mailExpanded.value = true
  emit('mail-folder', id)
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
onBeforeUnmount(() => { disposed = true; dictionaryRequest++; cancelDrag() })
</script>

<template>
  <nav ref="menu" id="workspace-menu" class="workspace-sidebar" :class="{ open, 'menu-reordering': dragged }" aria-label="Przestrzeń robocza" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="cancelDrag" @lostpointercapture="cancelDrag" @keydown.esc="cancelDrag">
    <div class="sidebar-heading"><button class="icon-button sidebar-close" aria-label="Zamknij menu" @click="emit('close')"><X :size="20" /></button></div>
    <p v-if="saving" class="menu-reorder-hint" role="status">Zapisywanie kolejności…</p>
    <div v-if="saveError" class="menu-save-error" role="alert"><p>{{ saveError }}</p><button @click="saveOrder">Spróbuj ponownie</button></div>
    <template v-for="item in items" :key="item.id">
      <button :data-menu-id="item.id" :class="{ active: active(item.id), 'menu-dragged': dragged === item.id }" :aria-current="active(item.id) && !groups[item.id] ? 'page' : undefined" :aria-expanded="groups[item.id] ? isExpanded(item.id) : undefined" :aria-controls="groups[item.id] ? `${item.id}-submenu` : undefined" :title="groups[item.id] ? `${isExpanded(item.id) ? 'Zwiń' : 'Rozwiń'}: ${item.label}` : `${item.label} — Ctrl + przeciągnięcie lub Ctrl + strzałki zmienia kolejność`" @pointerdown="pointerDown(item.id, $event)" @click="select(item.id, $event)" @keydown="keyMove(item.id, $event)">
        <component :is="item.icon" :size="18" /><span class="menu-item-label">{{ item.label }}</span><ChevronDown v-if="groups[item.id]" class="mail-menu-chevron" :class="{ expanded: isExpanded(item.id) }" :size="16" />
      </button>
      <div v-if="item.id === 'mail'" v-show="mailExpanded" id="mail-submenu" class="mail-folder-menu" role="group" aria-label="Centrum wiadomości">
        <button v-for="item in mailFolders" :key="item.id" :class="{ active: view === 'mail' && mailFolder === item.id }" :aria-current="view === 'mail' && mailFolder === item.id ? 'page' : undefined" :title="`Otwórz folder: ${item.label}`" @click="selectMailFolder(item.id, $event)"><component :is="item.icon" :size="16" />{{ item.label }}</button>
        <button :class="{ active: view === 'edelivery' }" :aria-current="view === 'edelivery' ? 'page' : undefined" @click="selectChild('edelivery', $event)"><Mail :size="16" />eDoręczenia</button>
      </div>
      <div v-else-if="children[item.id]" v-show="isExpanded(item.id)" :id="`${item.id}-submenu`" class="mail-folder-menu" role="group" :aria-label="item.label">
        <button v-for="child in visibleChildren(item.id)" :key="child.id" :class="{ active: view === child.id }" :aria-current="view === child.id ? 'page' : undefined" @click="selectChild(child.id, $event)"><component :is="child.icon" :size="16" />{{ child.label }}<span v-if="child.id === 'tasks' && tasksWaiting">({{ tasksWaiting }})</span><span v-if="child.id === 'surveys'">({{ activeSurveys }})</span></button>
      </div>
      <div v-else-if="item.id === 'dictionaries'" v-show="isExpanded(item.id)" id="dictionaries-submenu" class="mail-folder-menu" role="group" aria-label="Słowniki">
        <button :class="{ active: view === 'dictionaries' && !dictionaryId }" :aria-current="view === 'dictionaries' && !dictionaryId ? 'page' : undefined" @click="selectDictionary(null, $event)"><BookOpen :size="16" />Wszystkie słowniki</button>
        <button :class="{ active: view === 'dictionaries' && dictionaryId === 'ai' }" :aria-current="view === 'dictionaries' && dictionaryId === 'ai' ? 'page' : undefined" @click="selectDictionary('ai', $event)"><Sparkles :size="16" />AI</button>
        <button v-for="dictionary in dictionaryList" :key="dictionary.id" :class="{ active: view === 'dictionaries' && dictionaryId === dictionary.id }" :aria-current="view === 'dictionaries' && dictionaryId === dictionary.id ? 'page' : undefined" @click="selectDictionary(dictionary.id, $event)"><BookOpen :size="16" />{{ dictionary.name }}</button>
        <p v-if="dictionariesLoading" class="submenu-notice" role="status">Wczytywanie słowników…</p>
        <div v-if="dictionaryError" class="submenu-notice" role="alert"><p>{{ dictionaryError }}</p><button @click="loadDictionaries">Spróbuj ponownie</button></div>
      </div>
    </template>
    <span class="menu-announcement" role="status" aria-live="polite">{{ announcement }}</span>
  </nav>
</template>

<style scoped>
.menu-item-label { min-width:0; text-align:left; line-height:1.45; }
.sidebar-heading { display:none; }
@media(max-width:1000px) { .sidebar-heading { display:flex; justify-content:flex-end; padding-bottom:0; } }
.menu-reorder-hint { font-size:10px; line-height:1.5; color:var(--muted); padding:0 14px; margin:-8px 0 8px; }
.menu-reordering { user-select:none; cursor:grabbing; }
.menu-reordering > button { cursor:grabbing; }
.workspace-sidebar > button.menu-dragged { opacity:.6; outline:2px dashed var(--accent); outline-offset:-2px; }
.menu-announcement { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }
.menu-save-error { padding:0 14px; font-size:11px; color:var(--theme-danger, #a95353); }
.menu-save-error button { font-size:11px; padding:6px 9px; }
.mail-menu-chevron { margin-left:auto; transition:transform .15s; }.mail-menu-chevron.expanded { transform:rotate(180deg); }
.mail-folder-menu { display:grid; gap:3px; margin:-3px 0 4px 21px; padding-left:9px; border-left:1px solid var(--border); }
.mail-folder-menu button { width:100%; justify-content:flex-start; text-align:left; gap:9px; padding:10px 8px; border:0; background:transparent; color:var(--secondary); font-size:11px; }
.mail-folder-menu button svg { flex-shrink:0; }.mail-folder-menu button:hover { color:var(--accent); background:var(--surface-soft); }.mail-folder-menu button.active { color:var(--accent); background:var(--accent-soft); font-weight:600; }
.mail-folder-menu button { overflow-wrap:anywhere; min-width:0; }
.submenu-notice { color:var(--muted); font-size:11px; padding:0 8px; }
</style>
