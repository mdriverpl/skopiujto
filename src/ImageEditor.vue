<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { X, Save, RotateCcw, Image as ImageIcon, Crop, Expand, Link2, Info, MousePointer2, SlidersHorizontal } from 'lucide-vue-next'

import FolderTasks from './FolderTasks.vue'
import { resourceTasks } from './resourceTasks.js'
const props = defineProps({ file: Object, api: Function, taskData: Object })
const fileTasks = computed(() => resourceTasks(props.taskData, props.file, 'file'))
const emit = defineEmits(['close', 'saved'])
const info = ref(null), error = ref(''), busy = ref(false), loading = ref(true), canvas = ref(null)
const crop = reactive({ x: 0, y: 0, width: 1, height: 1 })
const output = reactive({ width: 1, height: 1 })
const keepRatio = ref(true)
const tab = ref('image')
let picture, start, disposed = false
const valid = computed(() => info.value?.can_edit && picture &&
  [crop.x, crop.y, crop.width, crop.height, output.width, output.height].every(Number.isInteger) &&
  crop.x >= 0 && crop.y >= 0 && crop.width > 0 && crop.height > 0 &&
  crop.x + crop.width <= info.value.width && crop.y + crop.height <= info.value.height &&
  output.width > 0 && output.height > 0 && output.width <= 10000 && output.height <= 10000 && output.width * output.height <= 40000000)
function draw() {
  if (!canvas.value || !picture) return
  const c = canvas.value, context = c.getContext('2d')
  c.width = Math.max(1, Math.round(Math.min(760 / info.value.width, 440 / info.value.height, 1) * info.value.width))
  c.height = Math.max(1, Math.round(c.width * info.value.height / info.value.width))
  context.drawImage(picture, 0, 0, c.width, c.height)
  if (!info.value.can_edit) return
  const sx = c.width / info.value.width, sy = c.height / info.value.height
  context.fillStyle = '#11182788'
  context.beginPath(); context.rect(0, 0, c.width, c.height)
  context.rect(crop.x * sx, crop.y * sy, crop.width * sx, crop.height * sy)
  context.fill('evenodd')
  context.strokeStyle = '#ffffff'; context.lineWidth = 2
  context.strokeRect(crop.x * sx, crop.y * sy, crop.width * sx, crop.height * sy)
}
function cropChanged() {
  output.width = crop.width; output.height = crop.height; draw()
}
function reset() {
  Object.assign(crop, { x: 0, y: 0, width: info.value.width, height: info.value.height }); cropChanged()
}
function resizeChanged(axis) {
  if (keepRatio.value) {
    if (axis === 'width') output.height = Math.max(1, Math.round(output.width * crop.height / crop.width))
    else output.width = Math.max(1, Math.round(output.height * crop.width / crop.height))
  }
}
function point(event) {
  const bounds = canvas.value.getBoundingClientRect()
  return { x: Math.max(0, Math.min(info.value.width, Math.round((event.clientX - bounds.left) / bounds.width * info.value.width))),
    y: Math.max(0, Math.min(info.value.height, Math.round((event.clientY - bounds.top) / bounds.height * info.value.height))) }
}
function down(event) {
  if (!info.value?.can_edit || busy.value || event.button !== 0) return
  start = point(event); canvas.value.setPointerCapture(event.pointerId)
}
function move(event) {
  if (!start || busy.value) return
  const end = point(event)
  if (end.x === start.x || end.y === start.y) return
  Object.assign(crop, { x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.abs(end.x - start.x), height: Math.abs(end.y - start.y) })
  cropChanged()
}
function up(event) { move(event); start = null }
async function save() {
  if (!valid.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    await props.api(`/documents/${props.file.id}/image`, 'POST', { ...crop, output_width: output.width, output_height: output.height, version: info.value.version })
    emit('saved')
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
function close() { if (!busy.value) emit('close') }
function escape(event) { if (event.key === 'Escape') close() }
onMounted(async () => {
  document.addEventListener('keydown', escape)
  try {
    info.value = await props.api(`/documents/${props.file.id}/image`)
    if (disposed) return
    if (info.value.width) {
      reset()
      picture = new window.Image()
      const loaded = new Promise((resolve, reject) => {
        picture.onload = resolve; picture.onerror = () => reject(new Error('Przeglądarka nie obsługuje podglądu tego obrazu.'))
      })
      picture.src = `/api/documents/${props.file.id}/preview?v=${info.value.version}`
      await loaded
    }
  } catch (err) { picture = null; error.value = err.message }
  finally { loading.value = false; await nextTick(); if (!disposed) draw() }
})
onBeforeUnmount(() => { disposed = true; document.removeEventListener('keydown', escape) })
</script>

<template>
  <div class="modal-backdrop">
    <section class="panel image-editor" role="dialog" aria-modal="true" aria-labelledby="image-editor-title">
      <header class="image-header">
        <div class="heading-mark"><ImageIcon :size="20" /></div>
        <div class="heading-text"><h2 id="image-editor-title">{{ info?.can_edit ? 'Edytuj obraz' : 'Obraz i metadane' }}</h2><p :title="file.filename">{{ file.filename }}</p></div>
        <button autofocus class="icon-button close-button" :disabled="busy" aria-label="Zamknij edytor obrazu" @click="close"><X :size="20" /></button>
      </header>
      <nav class="image-tabs" aria-label="Obraz i dane pliku">
        <button :class="{ active: tab === 'image' }" :aria-pressed="tab === 'image'" :disabled="busy" @click="tab = 'image'"><SlidersHorizontal :size="16" /> {{ info?.can_edit ? 'Kadrowanie i wymiary' : 'Podgląd' }}</button>
        <button :class="{ active: tab === 'metadata' }" :aria-pressed="tab === 'metadata'" :disabled="busy" @click="tab = 'metadata'"><Info :size="16" /> Metadane</button>
        <button v-if="fileTasks.length" :class="{ active: tab === 'tasks' }" :aria-pressed="tab === 'tasks'" :disabled="busy" @click="tab = 'tasks'">Zadania ({{ fileTasks.length }})</button>
      </nav>
      <div class="image-content">
        <FolderTasks v-if="tab === 'tasks'" embedded :document="file" :task-data="taskData" :busy="busy" />
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-if="loading" class="loading">Wczytywanie obrazu i metadanych…</p>
        <template v-else-if="info">
          <div v-show="tab === 'image'" class="image-workspace" :class="{ readonly: !info.can_edit }">
            <section class="image-preview" aria-label="Podgląd obrazu">
              <div class="preview-heading"><span>Podgląd</span><span v-if="info.width" class="dimension-tag">{{ info.width }} × {{ info.height }} px</span></div>
              <div v-if="info.width" class="crop-stage" :class="{ editable: info.can_edit }"><canvas ref="canvas" aria-label="Podgląd obrazu. Kadr można zaznaczyć przeciągnięciem lub podać w polach obok." @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="start = null" @lostpointercapture="start = null"></canvas></div>
              <p v-if="info.can_edit" class="preview-hint"><MousePointer2 :size="14" /> Przeciągnij po obrazie, aby zaznaczyć kadr.</p>
              <p v-else class="readonly-note">{{ info.reason || 'Podgląd do odczytu. Obraz może zmieniać jego autor z uprawnieniem do edycji.' }}</p>
            </section>
            <form v-if="info.can_edit" id="image-edit-form" class="image-tools" @submit.prevent="save">
              <fieldset :disabled="busy" class="tool-section"><legend><Crop :size="16" /> Kadrowanie</legend>
                <div class="tool-grid"><label>X (px)<input v-model.number="crop.x" type="number" min="0" :max="info.width - 1" required @input="cropChanged" /></label><label>Y (px)<input v-model.number="crop.y" type="number" min="0" :max="info.height - 1" required @input="cropChanged" /></label><label>Szerokość (px)<input v-model.number="crop.width" type="number" min="1" :max="info.width - crop.x" required @input="cropChanged" /></label><label>Wysokość (px)<input v-model.number="crop.height" type="number" min="1" :max="info.height - crop.y" required @input="cropChanged" /></label></div>
                <button class="text-button reset-button" type="button" @click="reset"><RotateCcw :size="14" /> Przywróć cały obraz</button>
              </fieldset>
              <fieldset :disabled="busy" class="tool-section resize-section"><legend><Expand :size="16" /> Rozdzielczość</legend>
                <div class="tool-grid"><label>Szerokość (px)<input v-model.number="output.width" type="number" min="1" max="10000" required @input="resizeChanged('width')" /></label><label>Wysokość (px)<input v-model.number="output.height" type="number" min="1" max="10000" required @input="resizeChanged('height')" /></label></div>
                <label class="ratio-option"><input v-model="keepRatio" type="checkbox" @change="resizeChanged('width')" /><Link2 :size="14" /> Zachowaj proporcje</label>
              </fieldset>
              <div class="output-summary"><span>Wymiary po zapisie</span><strong>{{ output.width || '—' }} × {{ output.height || '—' }} <small>px</small></strong></div>
              <p class="limit-note">Do 10 000 px na bok · 40 mln pikseli · 10 MB</p>
            </form>
          </div>
          <section v-show="tab === 'metadata'" class="image-metadata" aria-label="Tagi i dane pliku">
            <div class="metadata-heading"><h3>Dane pliku</h3><span>Tagi: {{ info.tags.length }}</span></div>
            <p class="metadata-note">Tagi EXIF są widoczne, jeśli plik je zawiera.</p>
            <table><thead><tr><th scope="col">Tag</th><th scope="col">Wartość</th></tr></thead><tbody><tr v-for="(tag, index) in info.tags" :key="index"><th scope="row">{{ tag.name }}</th><td>{{ tag.value }}</td></tr></tbody></table>
          </section>
        </template>
      </div>
      <footer class="image-footer">
        <p v-if="!loading && info?.can_edit && tab === 'image'">Zapis zastąpi obecny obraz.</p><p v-else class="footer-file" :title="file.filename">{{ file.filename }}</p>
        <div><button class="secondary-button" type="button" :disabled="busy" @click="close">{{ info?.can_edit && tab === 'image' ? 'Anuluj' : 'Zamknij' }}</button><button v-if="!loading && info?.can_edit && tab === 'image'" class="primary" type="submit" form="image-edit-form" :disabled="busy || !valid"><Save :size="16" /> {{ busy ? 'Zapisywanie…' : 'Zapisz obraz' }}</button></div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.image-editor { width: 1040px; max-width: 100%; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; border-radius: 18px; box-shadow: 0 24px 90px #25283d26; }
.image-header { display: flex; align-items: center; gap: 12px; padding: 22px 26px 18px; flex-shrink: 0; }
.heading-mark { display: flex; align-items: center; justify-content: center; width: 42px; height: 42px; border-radius: 12px; background: var(--accent-soft); color: var(--accent); flex-shrink: 0; }
.heading-text { flex: 1; min-width: 0; }
.heading-text h2 { margin: 0; font-size: 18px; letter-spacing: -.35px; }
.heading-text p { margin: 5px 0 0; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.close-button { align-self: flex-start; color: var(--muted); }
.image-tabs { display: flex; gap: 22px; padding: 0 26px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.image-tabs button { position: relative; border: none; border-radius: 0; background: transparent; padding: 11px 0 13px; color: var(--muted); font-size: 13px; font-weight: 500; }
.image-tabs button.active { color: var(--accent); }
.image-tabs button.active::after { content: ''; position: absolute; height: 2px; background: var(--accent); bottom: -1px; left: 0; right: 0; border-radius: 2px; }
.image-content { overflow-y: auto; min-height: 0; padding: 24px 26px; }
.image-content .error { font-size: 12px; line-height: 1.6; margin: 0 0 18px; padding: 11px 13px; }
.image-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 242px; gap: 24px; align-items: start; }
.image-workspace.readonly { grid-template-columns: minmax(0, 1fr); }
.image-preview { min-width: 0; }
.preview-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; color: var(--secondary); font-size: 12px; }
.dimension-tag { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
.crop-stage { display: flex; justify-content: center; align-items: center; padding: 18px; min-height: 320px; border: 1px solid var(--border); border-radius: 12px; background-color: var(--theme-surface-soft, #f5f6fa); background-image: linear-gradient(45deg, #e9ecf355 25%, transparent 25%, transparent 75%, #e9ecf355 75%), linear-gradient(45deg, #e9ecf355 25%, transparent 25%, transparent 75%, #e9ecf355 75%); background-size: 20px 20px; background-position: 0 0, 10px 10px; }
canvas { display: block; max-width: 100%; height: auto; box-shadow: 0 3px 16px #25283d0d; }
.crop-stage.editable canvas { touch-action: none; cursor: crosshair; }
.preview-hint { display: flex; align-items: center; justify-content: center; gap: 6px; margin: 12px 0 0; color: var(--muted); font-size: 11px; }
.readonly-note { margin: 12px 0 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
.image-tools { gap: 0; min-width: 0; }
.tool-section { min-width: 0; border: none; padding: 0; border-radius: 0; margin: 0; }
.tool-section legend { display: flex; align-items: center; gap: 7px; padding: 0; color: var(--text); font-size: 12px; font-weight: 600; margin-bottom: 16px; }
.tool-section legend svg { color: var(--theme-accent, #9993b2); }
.tool-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.tool-grid label { margin: 0; gap: 6px; font-size: 11px; color: var(--muted); }
.tool-grid input { padding: 9px 10px; border-color: var(--border); font-size: 13px; border-radius: 8px; font-variant-numeric: tabular-nums; }
.text-button { padding: 5px 0; border: none; color: var(--muted); background: transparent; font-size: 11px; justify-content: flex-start; }
.text-button:hover { color: var(--accent); background: transparent; }
.reset-button { margin: 10px 0 18px; }
.resize-section { padding-top: 0; margin-top: 4px; }
.ratio-option { display: flex; flex-direction: row; align-items: center; gap: 7px; margin: 12px 0 20px; color: var(--muted); font-size: 11px; }
.ratio-option input { width: 13px; height: 13px; accent-color: var(--accent); }
.ratio-option svg { color: var(--theme-accent, #a09ab9); }
.output-summary { display: flex; flex-direction: column; gap: 7px; background: var(--accent-soft); border-radius: 10px; padding: 14px; color: var(--theme-accent, #8f84b1); font-size: 11px; }
.output-summary strong { color: var(--accent); font-size: 18px; letter-spacing: -.4px; font-weight: 500; overflow-wrap: anywhere; }
.output-summary small { font-size: 11px; color: var(--theme-accent, #9b90bf); font-weight: 400; }
.limit-note { font-size: 10px; color: var(--muted); line-height: 1.6; margin: 10px 0 0; }
.metadata-heading { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.metadata-heading h3 { font-size: 13px; margin: 0; }
.metadata-heading span { font-size: 11px; color: var(--muted); }
.metadata-note { font-size: 12px; color: var(--muted); margin: 8px 0 18px; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
th, td { text-align: left; vertical-align: top; padding: 11px 12px; border-bottom: 1px solid var(--border); overflow-wrap: anywhere; line-height: 1.6; }
th { width: 34%; font-weight: 500; color: var(--secondary); }
thead th { background: var(--page-bg); color: var(--muted); font-size: 11px; }
td { color: var(--text); }
.image-footer { display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-shrink: 0; padding: 15px 26px; border-top: 1px solid var(--border); }
.image-footer p { font-size: 11px; color: var(--muted); margin: 0; min-width: 0; }
.image-footer .footer-file { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.image-footer > div { display: flex; gap: 8px; flex-shrink: 0; }
.image-footer button { font-size: 12px; padding: 10px 14px; }
.secondary-button { border: none; background: transparent; color: var(--muted); }
@media (max-width: 760px) {
  .image-workspace { grid-template-columns: minmax(0, 1fr); gap: 22px; }
  .image-tools { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
  .resize-section { margin-top: 0; }
  .output-summary { grid-column: 1 / -1; flex-direction: row; align-items: center; justify-content: space-between; }
  .limit-note { grid-column: 1 / -1; margin: -10px 0 0; }
  .crop-stage { min-height: 200px; }
}
@media (max-width: 480px) {
  .image-editor { max-height: 92vh; }
  .image-header { padding: 18px 18px 14px; gap: 10px; }
  .heading-mark { width: 36px; height: 36px; }
  .heading-text h2 { font-size: 16px; }
  .heading-text p { font-size: 11px; }
  .image-tabs { padding: 0 18px; gap: 18px; }
  .image-tabs button { font-size: 12px; }
  .image-content { padding: 18px; }
  .image-tools { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .reset-button { margin-bottom: 0; }
  .ratio-option { margin-bottom: 0; }
  .crop-stage { padding: 12px; min-height: 160px; }
  .image-footer { padding: 12px 18px; flex-wrap: wrap; gap: 10px; }
  .image-footer > div { margin-left: auto; }
}
</style>
