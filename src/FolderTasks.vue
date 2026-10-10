<script setup>
import { computed } from 'vue'
import { ClipboardList, ClipboardPlus, ArrowUpRight, CalendarDays, Check, Clock3, X } from 'lucide-vue-next'
import { resourceTasks } from './resourceTasks.js'

const props = defineProps({ folder: Object, document: Object, taskData: Object, busy: Boolean, embedded: Boolean })
const emit = defineEmits(['add-task', 'open-tasks'])
const labels = { todo: 'Do wykonania', in_progress: 'W toku', done: 'Wykonano', cancelled: 'Anulowano', waiting: 'Oczekuje', accepted: 'Zaakceptowano', expired: 'Wygasło', revoked: 'Cofnięto', failed: 'Błąd wysyłki', sending: 'Wysyłanie' }
const pending = item => ['todo', 'in_progress', 'waiting', 'sending'].includes(item.status)
const tasks = computed(() => resourceTasks(props.taskData, props.document || props.folder, props.document ? 'file' : 'folder'))
const waiting = computed(() => tasks.value.filter(pending).length)
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
</script>

<template>
  <section class="folder-tasks" :class="{ embedded }" aria-label="Zadania powiązane">
    <header v-if="!embedded">
      <div class="folder-tasks-heading"><span class="section-icon"><ClipboardList :size="20" /></span><div><h2>{{ document ? 'Zadania pliku' : 'Zadania katalogu' }} <span>{{ tasks.length }}</span></h2><p>{{ waiting ? `${waiting} do wykonania · historia poniżej` : 'Historia zadań przypisanych do tego katalogu' }}</p></div></div>
      <div class="section-actions"><button :disabled="busy" @click="emit('open-tasks')"><ArrowUpRight :size="15" /> Wszystkie zadania</button><button v-if="folder?.permissions?.read" class="icon-button" :disabled="busy" title="Dodaj zadanie" aria-label="Dodaj zadanie do otwartego katalogu" @click="emit('add-task', folder)"><ClipboardPlus :size="19" /></button></div>
    </header>
    <div v-if="tasks.length" class="folder-task-cards">
      <article v-for="item in tasks" :key="item.key" class="folder-task-card" :class="item.status">
        <div class="card-heading"><span class="status-icon"><Check v-if="['done', 'accepted'].includes(item.status)" :size="17" /><X v-else-if="item.status === 'cancelled'" :size="17" /><Clock3 v-else :size="17" /></span><h3>{{ item.title }}</h3><span class="status-label">{{ labels[item.status] || item.status }}</span></div>
        <p v-if="item.description" class="task-description">{{ item.description }}</p>
        <div class="task-people"><span>Dla: <strong>{{ item.assignee_name }}</strong></span><span>Od: {{ item.sender_name }}</span></div>
        <footer><span v-if="item.due_at" :class="{ overdue: pending(item) && new Date(item.due_at).getTime() < Date.now() }"><CalendarDays :size="13" /> Termin: {{ date(item.due_at) }}</span><span v-if="item.completed_at">Zakończono {{ date(item.completed_at) }}</span><span v-else>Dodano {{ date(item.created_at) }}</span></footer>
      </article>
    </div>
    <div v-else class="folder-tasks-empty"><ClipboardList :size="25" /><p>Brak powiązanych zadań dla Ciebie lub wysłanych przez Ciebie.</p></div>
  </section>
</template>

<style scoped>
.folder-tasks.embedded { margin: 0; border: none; padding: 0; }
.folder-tasks { margin-top: 30px; border-top: 1px solid var(--border); padding-top: 24px; }
header, .folder-tasks-heading, .section-actions, .card-heading { display: flex; align-items: center; gap: 12px; }
header { justify-content: space-between; flex-wrap: wrap; margin-bottom: 18px; }
.section-icon { display: flex; padding: 11px; border-radius: 12px; background: var(--accent-soft); color: var(--accent); }
h2 { margin: 0; font-size: 17px; }h2 span { margin-left: 6px; font-size: 11px; padding: 3px 7px; background: var(--accent-soft); color: var(--accent); border-radius: 6px; }
header p { margin: 5px 0 0; color: var(--muted); font-size: 12px; }.section-actions { gap: 7px; }.section-actions button { font-size: 11px; }
.folder-task-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap: 14px; }
.folder-task-card { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 18px; min-width: 0; }
.card-heading { align-items: flex-start; gap: 9px; }.card-heading h3 { margin: 2px 0; font-size: 14px; flex: 1; overflow-wrap: anywhere; }
.status-icon { display: flex; padding: 5px; border-radius: 7px; color: var(--warning); background: var(--warning-soft); }.status-label { font-size: 10px; color: var(--warning); padding-top: 6px; white-space: nowrap; }
.done .status-icon, .accepted .status-icon { color: var(--success); background: var(--success-soft); }.done .status-label, .accepted .status-label { color: var(--success); }.cancelled .status-icon { color: var(--muted); background: var(--surface-soft); }.cancelled .status-label { color: var(--muted); }.in_progress .status-icon { color: var(--accent); background: var(--accent-soft); }.in_progress .status-label { color: var(--accent); }
.task-description { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.7; color: var(--secondary); margin: 12px 0; }
.task-people { display: flex; flex-wrap: wrap; gap: 5px 14px; font-size: 11px; color: var(--muted); margin-top: 14px; overflow-wrap: anywhere; }.task-people strong { color: var(--secondary); font-weight: 500; }
footer { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--surface-soft); display: flex; flex-wrap: wrap; gap: 7px 14px; color: var(--muted); font-size: 10px; }footer span { display: inline-flex; align-items: center; gap: 5px; }footer .overdue { color: var(--danger); }
.folder-tasks-empty { display: flex; align-items: center; gap: 12px; color: var(--muted); background: var(--surface-soft); border: 1px dashed var(--theme-border, #e0e2ee); border-radius: 12px; padding: 20px; }.folder-tasks-empty p { margin: 0; font-size: 12px; }
</style>
