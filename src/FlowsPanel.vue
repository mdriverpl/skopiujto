<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { GitBranch, Plus, Search, RefreshCw, X, Save, Pencil, Trash2, ArrowDown, ArrowUp, Mail, FileText, ClipboardList, CheckCircle2, Bell, Folder, Play, ChevronRight } from 'lucide-vue-next'
const props = defineProps({ api: Function, currentUser: Object })
const flows = ref([]), options = ref({ users: [], groups: [], folders: [] }), search = ref('')
const draft = ref(null), dialog = ref(null), loading = ref(true), busy = ref(false), error = ref(''), formError = ref(''), notice = ref('')
const canManage = computed(() => props.currentUser?.role === 'admin' && !props.currentUser?.impersonation)
const filtered = computed(() => flows.value.filter(item => `${item.name} ${item.description}`.toLocaleLowerCase('pl').includes(search.value.toLocaleLowerCase('pl'))))
const triggers = { manual: 'Ręcznie', email_received: 'Nowy e-mail', document_added: 'Nowy dokument' }
const stepTypes = { approval: { label: 'Akceptacja', icon: CheckCircle2 }, task: { label: 'Zadanie', icon: ClipboardList }, save_document: { label: 'Zapisz dokument', icon: Folder }, notification: { label: 'Powiadomienie', icon: Bell } }
const date = value => new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeZone: 'Europe/Warsaw' }).format(new Date(value))
let sequence = 0, initial = ''
function newStep(kind = 'task') { return { id: `step-${Date.now()}-${++sequence}`, kind, title: stepTypes[kind].label, description: '', target_type: 'user', target_id: props.currentUser?.id || '', folder_id: '', due_days: 2, rejection: 'return' } }
watch(draft, value => { if (value) dialog.value?.showModal(); else dialog.value?.close() }, { flush: 'post' })
async function load() {
  if (busy.value) return
  loading.value = true; error.value = ''
  try {
    const result = await Promise.all([props.api('/flows'), props.api('/flows/options')])
    flows.value = result[0]; options.value = result[1]
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}
function open(item = null) {
  if (busy.value) return
  draft.value = item ? JSON.parse(JSON.stringify(item)) : { name: '', description: '', trigger: { event: 'manual', subject_contains: '', sender_contains: '', attachments_only: false }, steps: [newStep()] }
  initial = JSON.stringify(draft.value); formError.value = ''; notice.value = ''
}
function close() {
  if (busy.value) return
  if (canManage.value && JSON.stringify(draft.value) !== initial && !window.confirm('Zamknąć Flow bez zapisywania zmian?')) return
  draft.value = null
}
function addStep(kind = 'task') { if (draft.value.steps.length < 40) draft.value.steps.push(newStep(kind)) }
function moveStep(index, offset) {
  const next = index + offset
  if (next < 0 || next >= draft.value.steps.length) return
  const steps = draft.value.steps
  ;[steps[index], steps[next]] = [steps[next], steps[index]]
}
function changeKind(step, kind) {
  if (step.title === stepTypes[step.kind].label) step.title = stepTypes[kind].label
  step.kind = kind
}
function targetOptions(step) { return step.target_type === 'group' ? options.value.groups : options.value.users }
function useInvoiceExample() {
  if (JSON.stringify(draft.value) !== initial && !window.confirm('Zastąpić bieżący formularz przykładem obiegu faktury?')) return
  const approval = newStep('approval'), payment = newStep('task')
  approval.title = 'Akceptacja faktury'; approval.description = 'Sprawdź fakturę i zaakceptuj ją lub zwróć z komentarzem.'
  payment.title = 'Opłać fakturę'; payment.description = 'Zrealizuj płatność i potwierdź jej wykonanie.'
  for (const [step, pattern] of [[approval, /rozlicz|księg/i], [payment, /finans/i]]) {
    const group = options.value.groups.find(item => pattern.test(item.name))
    if (group) { step.target_type = 'group'; step.target_id = group.id }
  }
  draft.value.name = 'Obieg faktury'; draft.value.description = 'Akceptacja w dziale rozliczeń, następnie płatność w dziale finansowym.'
  draft.value.trigger = { event: 'email_received', subject_contains: 'faktura', sender_contains: '', attachments_only: true }
  draft.value.steps = [approval, payment]
}
function payload() {
  return { name: draft.value.name.trim(), description: draft.value.description, trigger: { ...draft.value.trigger },
    steps: draft.value.steps.map(step => ({ ...step, target_id: step.kind === 'save_document' ? null : step.target_id || null, folder_id: step.kind === 'save_document' ? step.folder_id || null : null })),
    ...(draft.value.id ? { version: draft.value.version } : {}) }
}
async function save() {
  if (busy.value || !canManage.value || !draft.value) return
  formError.value = ''
  if (!draft.value.name.trim() || !draft.value.steps.length) { formError.value = 'Podaj nazwę Flow i dodaj przynajmniej jeden krok.'; return }
  if (draft.value.steps.some(step => !step.title.trim() || (step.kind === 'save_document' ? !step.folder_id : !step.target_id))) { formError.value = 'Uzupełnij nazwy kroków oraz wybierz osoby, grupy lub katalogi.'; return }
  busy.value = true
  try {
    const saved = await props.api(draft.value.id ? `/flows/${draft.value.id}` : '/flows', draft.value.id ? 'PUT' : 'POST', payload())
    flows.value = [saved, ...flows.value.filter(item => item.id !== saved.id)]
    draft.value = null; notice.value = 'Flow zapisane jako szkic.'
  } catch (err) { formError.value = err.message }
  finally { busy.value = false }
}
async function remove(item) {
  if (busy.value || !canManage.value || !window.confirm(`Usunąć Flow „${item.name}”?`)) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await props.api(`/flows/${item.id}?version=${item.version}`, 'DELETE'); flows.value = flows.value.filter(flow => flow.id !== item.id); notice.value = 'Flow usunięte.' }
  catch (err) { error.value = err.message }
  finally { busy.value = false }
}
onMounted(load)
</script>
<template>
  <section class="flows-page">
    <header class="page-menu flow-heading"><Teleport to="#workspace-title"><div><h1>Flow <span>{{ flows.length }}</span></h1><p>Buduj firmowe procesy krok po kroku.</p></div></Teleport><div class="flow-actions"><button class="icon-button" :disabled="busy || loading" aria-label="Odśwież Flow" @click="load"><RefreshCw :size="17" /></button><button v-if="canManage" class="primary" :disabled="busy || loading || !!error" @click="open()"><Plus :size="17" /> Dodaj Flow</button></div></header>
    <Teleport to="#workspace-search"><div class="search"><Search :size="17" /><input v-model="search" aria-label="Szukaj Flow" placeholder="Szukaj procesu…" /></div></Teleport>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="notice" class="success" role="status">{{ notice }}</p>
    <div class="flow-info"><GitBranch :size="20" /><p>Projektuj i zapisuj szkice procesów. Automatyczne wykonywanie kroków nie jest jeszcze dostępne.</p></div>
    <p v-if="loading" class="muted" role="status">Wczytywanie Flow…</p>
    <div v-else class="flow-list"><article v-for="item in filtered" :key="item.id" class="panel flow-row"><span class="flow-art" aria-hidden="true"><GitBranch :size="25" :stroke-width="1.5" /></span><div class="flow-summary"><h2><button @click="open(item)">{{ item.name }}</button><span class="flow-draft">Szkic</span></h2><p v-if="item.description">{{ item.description }}</p><small>{{ triggers[item.trigger.event] }} · {{ item.steps.length }} kroków · Zmieniono {{ date(item.updated_at) }}</small><div class="flow-mini"><span v-for="step in item.steps.slice(0, 4)" :key="step.id"><component :is="stepTypes[step.kind].icon" :size="12" />{{ step.title }}<ChevronRight :size="12" /></span><small v-if="item.steps.length > 4">+{{ item.steps.length - 4 }}</small></div></div><div class="flow-row-actions"><button :disabled="busy" :aria-label="`${canManage ? 'Edytuj' : 'Podgląd'} Flow: ${item.name}`" @click="open(item)"><Pencil :size="15" />{{ canManage ? 'Edytuj' : 'Podgląd' }}</button><button v-if="canManage" class="icon-button" :disabled="busy" :aria-label="`Usuń Flow: ${item.name}`" @click="remove(item)"><Trash2 :size="16" /></button></div></article></div>
    <div v-if="!loading && !filtered.length && !error" class="panel flow-empty"><span class="flow-art"><GitBranch :size="32" :stroke-width="1.5" /></span><h2>{{ search ? 'Brak pasujących Flow' : 'Zbuduj swój pierwszy proces' }}</h2><p>{{ search ? 'Zmień wyszukiwanie.' : 'Ustal, co rozpoczyna proces, kto ma wykonać zadania i jak przebiega akceptacja.' }}</p><button v-if="canManage && !search" class="primary" @click="open()"><Plus :size="16" /> Dodaj Flow</button></div>
    <dialog ref="dialog" class="flow-dialog" aria-labelledby="flow-title" @cancel.prevent="close">
      <form v-if="draft" @submit.prevent="save">
        <header class="flow-dialog-heading"><span class="flow-art" aria-hidden="true"><GitBranch :size="27" :stroke-width="1.5" /></span><div><small>PROJEKTANT PROCESU · SZKIC</small><h2 id="flow-title">{{ draft.id ? (canManage ? 'Edytuj Flow' : 'Podgląd Flow') : 'Nowe Flow' }}</h2></div><button type="button" class="icon-button" :disabled="busy" aria-label="Zamknij Flow" @click="close"><X :size="19" /></button></header>
        <div class="flow-form-body"><p v-if="formError" class="error" role="alert">{{ formError }}</p>
          <fieldset :disabled="busy || !canManage"><div class="flow-basics"><label>Nazwa Flow<input v-model="draft.name" autofocus required maxlength="200" placeholder="np. Obieg faktury" /></label><label>Opis <small>opcjonalnie</small><textarea v-model="draft.description" rows="2" maxlength="2000" placeholder="Do czego służy ten proces?" /></label></div>
          <button v-if="canManage" type="button" class="flow-example" @click="useInvoiceExample"><FileText :size="16" /> Wstaw przykład: obieg faktury</button>
          <section class="flow-trigger"><div class="flow-section-title"><span class="flow-start-icon"><Play :size="16" /></span><div><h3>Co rozpoczyna proces?</h3><p>Wybierz zdarzenie i warunki rozpoczęcia.</p></div></div><label>Początek<select v-model="draft.trigger.event"><option v-for="(label, key) in triggers" :key="key" :value="key">{{ label }}</option></select></label><div v-if="draft.trigger.event === 'email_received'" class="flow-fields"><label>Temat zawiera<input v-model="draft.trigger.subject_contains" maxlength="200" placeholder="np. faktura" /></label><label>Nadawca zawiera<input v-model="draft.trigger.sender_contains" maxlength="254" placeholder="np. @kontrahent.pl" /></label><label class="flow-checkbox"><input v-model="draft.trigger.attachments_only" type="checkbox" /> Tylko wiadomości z załącznikiem</label></div></section>
          <div class="flow-step-heading"><h3>Kolejne kroki <span>{{ draft.steps.length }}</span></h3><small>Wykonywane w kolejności od góry.</small></div>
          <ol class="flow-steps"><li v-for="(step, index) in draft.steps" :key="step.id" class="flow-step"><div class="flow-step-top"><span class="flow-step-number">{{ index + 1 }}</span><component :is="stepTypes[step.kind].icon" :size="18" /><strong>{{ stepTypes[step.kind].label }}</strong><div v-if="canManage" class="flow-step-tools"><button type="button" :disabled="index === 0" :aria-label="`Przenieś krok ${index + 1} w górę`" @click="moveStep(index, -1)"><ArrowUp :size="14" /></button><button type="button" :disabled="index === draft.steps.length - 1" :aria-label="`Przenieś krok ${index + 1} w dół`" @click="moveStep(index, 1)"><ArrowDown :size="14" /></button><button type="button" :disabled="draft.steps.length === 1" :aria-label="`Usuń krok ${index + 1}`" @click="draft.steps.splice(index, 1)"><Trash2 :size="14" /></button></div></div><div class="flow-fields"><label>Rodzaj kroku<select :value="step.kind" @change="changeKind(step, $event.target.value)"><option v-for="(type, key) in stepTypes" :key="key" :value="key">{{ type.label }}</option></select></label><label>Nazwa kroku<input v-model="step.title" maxlength="200" required /></label>
          <template v-if="step.kind !== 'save_document'"><label>Przekaż do<select v-model="step.target_type" @change="step.target_id = ''"><option value="user">Osoba</option><option value="group">Grupa / dział</option></select></label><label>{{ step.target_type === 'group' ? 'Grupa / dział' : 'Osoba' }}<select v-model="step.target_id" required><option disabled value="">Wybierz…</option><option v-for="target in targetOptions(step)" :key="target.id" :value="target.id">{{ target.name }}</option></select></label></template><label v-else class="flow-wide">Katalog docelowy<select v-model="step.folder_id" required><option disabled value="">Wybierz katalog…</option><option v-for="folder in options.folders" :key="folder.id" :value="folder.id">{{ folder.name }}</option></select></label>
          <label v-if="['approval', 'task'].includes(step.kind)">Termin wykonania (dni)<input v-model.number="step.due_days" type="number" min="1" max="365" required /></label><label v-if="step.kind === 'approval'">W razie odrzucenia<select v-model="step.rejection"><option value="return">Zwróć do poprawy i ponownej akceptacji</option><option value="stop">Zakończ proces jako odrzucony</option></select></label><label class="flow-wide">Instrukcja <small>opcjonalnie</small><textarea v-model="step.description" rows="2" maxlength="2000" placeholder="Opisz, co należy zrobić w tym kroku…" /></label></div><p v-if="step.kind === 'approval'" class="flow-approval-note"><CheckCircle2 :size="13" /> Następny krok dopiero po akceptacji.</p></li></ol>
          <button v-if="canManage" type="button" class="flow-add-step" :disabled="draft.steps.length >= 40" @click="addStep()"><Plus :size="16" /> Dodaj krok</button>
          <div class="flow-end"><CheckCircle2 :size="17" /> Koniec procesu</div></fieldset>
        </div><footer class="flow-dialog-footer"><span>Zapisujesz projekt procesu.</span><button type="button" :disabled="busy" @click="close">{{ canManage ? 'Anuluj' : 'Zamknij' }}</button><button v-if="canManage" class="primary" type="submit" :disabled="busy"><Save :size="15" /> {{ busy ? 'Zapisywanie…' : 'Zapisz Flow' }}</button></footer>
      </form>
    </dialog>
  </section>
</template>
<style scoped>
.flow-heading,.flow-actions,.flow-row-actions { display:flex; align-items:center; gap:10px; }.flow-heading { margin-bottom:20px; }.flow-heading h1 { font-size:24px; margin:0; }.flow-heading h1 span { color:var(--accent); background:var(--accent-soft); border-radius:6px; font-size:11px; padding:4px 7px; margin-left:6px; }.flow-heading p { color:var(--muted); font-size:12px; }.flow-actions button { font-size:12px; }.search { max-width:100%; }
.flow-info { display:flex; gap:10px; align-items:center; color:var(--muted); margin:16px 0 20px; font-size:12px; line-height:1.6; }.flow-info svg { color:var(--accent); flex-shrink:0; }.flow-info p { margin:0; }.flow-list { display:grid; gap:12px; }.flow-row { display:flex; align-items:flex-start; gap:16px; padding:18px; border-radius:12px; }.flow-art { display:inline-flex; align-items:center; justify-content:center; padding:12px; color:var(--accent); background:var(--accent-soft); border-radius:13px; flex-shrink:0; }.flow-summary { flex:1; min-width:0; overflow-wrap:anywhere; }.flow-summary h2 { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin:0 0 8px; font-size:14px; }.flow-summary h2 button { border:0; background:transparent; font:inherit; text-align:left; padding:0; overflow-wrap:anywhere; }.flow-draft { font-size:10px; font-weight:400; color:var(--muted); background:var(--surface-soft); border-radius:5px; padding:3px 6px; }.flow-summary p { color:var(--secondary); font-size:12px; line-height:1.6; margin:6px 0; }.flow-summary > small { color:var(--muted); font-size:10px; }.flow-row-actions button { padding:7px 9px; font-size:11px; }.flow-mini { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:12px; }.flow-mini > span { display:inline-flex; gap:5px; align-items:center; font-size:10px; color:var(--accent); }.flow-mini small { font-size:10px; }.flow-empty { padding:40px 20px; text-align:center; }.flow-empty h2 { font-size:17px; margin:16px 0 8px; }.flow-empty p { color:var(--muted); font-size:12px; line-height:1.7; }.flow-empty button { margin:16px auto 0; font-size:12px; }
.flow-dialog { width:min(800px,calc(100vw - 32px)); max-height:calc(100dvh - 32px); padding:0; border:1px solid var(--border); border-radius:16px; background:var(--surface); color:var(--text); box-shadow:0 24px 70px #0002; }.flow-dialog[open] { display:flex; flex-direction:column; }.flow-dialog::backdrop { background:#13213966; backdrop-filter:blur(4px); }.flow-dialog form { min-height:0; display:flex; flex-direction:column; overflow:hidden; }.flow-dialog-heading { display:flex; align-items:center; gap:14px; padding:16px 20px; border-bottom:1px solid var(--border); background:linear-gradient(120deg,var(--accent-soft),var(--surface) 80%); flex-shrink:0; }.flow-dialog-heading > div { flex:1; min-width:0; }.flow-dialog-heading small { font-size:9px; letter-spacing:.5px; color:var(--accent); }.flow-dialog-heading h2 { font-size:18px; margin:5px 0 0; }.flow-dialog-heading button { padding:7px; }.flow-form-body { padding:20px; overflow:auto; min-height:0; overscroll-behavior:contain; }.flow-dialog fieldset { margin:0; border:0; padding:0; min-width:0; }.flow-dialog label { gap:6px; font-size:11px; font-weight:400; color:var(--secondary); }.flow-dialog label small { color:var(--muted); font-size:10px; }.flow-dialog input,.flow-dialog select,.flow-dialog textarea { width:100%; padding:8px 10px; font-size:12px; border-radius:7px; }.flow-basics { display:grid; gap:12px; }.flow-example { margin:12px 0 20px; padding:7px 10px; color:var(--accent); background:var(--accent-soft); border-color:transparent; font-size:11px; }.flow-trigger { border:1px solid var(--border); border-radius:12px; padding:16px; }.flow-section-title { display:flex; align-items:center; gap:10px; margin-bottom:14px; }.flow-start-icon { display:flex; padding:9px; border-radius:9px; color:var(--accent); background:var(--accent-soft); }.flow-section-title h3,.flow-step-heading h3 { font-size:13px; margin:0; }.flow-section-title p { font-size:11px; color:var(--muted); margin:4px 0 0; }.flow-fields { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:12px; margin-top:12px; }.flow-wide { grid-column:1 / -1; }.flow-fields .flow-checkbox { display:flex; align-items:center; flex-direction:row; grid-column:1 / -1; }.flow-checkbox input { width:auto; }.flow-step-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:24px 0 12px; }.flow-step-heading h3 span { color:var(--accent); font-size:11px; margin-left:5px; }.flow-step-heading small { color:var(--muted); font-size:10px; }.flow-steps { padding:0; margin:0; list-style:none; display:grid; gap:16px; }.flow-step { border:1px solid var(--border); border-radius:12px; padding:14px; position:relative; }.flow-step:not(:last-child)::after { content:''; position:absolute; left:29px; top:100%; height:17px; border-left:2px solid var(--border); }.flow-step-top { display:flex; align-items:center; gap:8px; color:var(--accent); }.flow-step-top strong { font-size:12px; font-weight:500; }.flow-step-number { display:flex; justify-content:center; align-items:center; width:28px; height:28px; border-radius:8px; font-size:11px; background:var(--accent-soft); }.flow-step-tools { margin-left:auto; display:flex; gap:3px; }.flow-step-tools button { padding:5px; border:0; background:transparent; color:var(--muted); }.flow-approval-note { display:flex; align-items:center; gap:6px; font-size:10px; color:var(--accent); margin:12px 0 0; }.flow-add-step { width:100%; margin-top:14px; padding:10px; border:1px dashed var(--border); color:var(--accent); font-size:12px; background:transparent; }.flow-end { display:flex; align-items:center; justify-content:center; gap:7px; padding:18px 0 0; color:var(--muted); font-size:11px; }.flow-dialog-footer { display:flex; align-items:center; gap:8px; flex-shrink:0; padding:12px 20px; border-top:1px solid var(--border); }.flow-dialog-footer > span { margin-right:auto; color:var(--muted); font-size:10px; }.flow-dialog-footer button { padding:8px 12px; font-size:12px; }
@media(max-width:600px) { .flow-dialog { width:calc(100vw - 20px); max-height:calc(100dvh - 20px); }.flow-dialog-heading,.flow-form-body,.flow-dialog-footer { padding:14px; }.flow-fields { grid-template-columns:minmax(0,1fr); }.flow-wide,.flow-fields .flow-checkbox { grid-column:1; }.flow-step-heading { align-items:flex-start; flex-direction:column; }.flow-dialog-footer > span { display:none; }.flow-dialog-footer { justify-content:flex-end; }.flow-row { flex-wrap:wrap; gap:12px; padding:14px; }.flow-row-actions { margin-left:auto; }.flow-summary { min-width:180px; }.flow-dialog-heading .flow-art { padding:9px; } }
</style>
