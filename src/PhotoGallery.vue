<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Images, Grid3X3, List, ChevronLeft, ChevronRight, X, Download, ZoomIn, ZoomOut, Maximize, Minimize, Play, Pause, PanelBottom, RotateCcw, ImageOff } from 'lucide-vue-next'
const props = defineProps({ images: { type: Array, default: () => [] }, showGrid: Boolean })
function preference(key, allowed, fallback) {
  try { const value = globalThis.localStorage?.getItem(key); return allowed.includes(value) ? value : fallback } catch { return fallback }
}
const thumbnailSize = ref(preference('public-gallery-size', ['small', 'medium', 'large'], 'medium'))
const layout = ref(preference('public-gallery-layout', ['grid', 'list'], 'grid'))
const activeId = ref(null), dialog = ref(null), imageElement = ref(null), strip = ref(null)
const zoom = ref(1), pan = ref({ x: 0, y: 0 }), showThumbnails = ref(true), playing = ref(false)
const imageLoading = ref(false), imageError = ref(false), retry = ref(0), fullscreen = ref(false)
const failedThumbnails = ref({})
let timer = null, returnFocus = null, previousOverflow = '', locked = false, pointer = null
const activeIndex = computed(() => props.images.findIndex(image => image.id === activeId.value))
const active = computed(() => props.images[activeIndex.value] || null)
const activeSource = computed(() => active.value ? active.value.src + (retry.value ? `${active.value.src.includes('?') ? '&' : '?'}retry=${retry.value}` : '') : '')
function setPreference(key, value) { try { globalThis.localStorage?.setItem(key, value) } catch {} }
function setSize(value) { thumbnailSize.value = value; setPreference('public-gallery-size', value) }
function setLayout(value) { layout.value = value; setPreference('public-gallery-layout', value) }
function stop() { if (timer !== null) clearInterval(timer); timer = null; playing.value = false }
function resetImage() {
  zoom.value = 1; pan.value = { x: 0, y: 0 }; pointer = null
  imageLoading.value = true; imageError.value = false; retry.value = 0
}
async function revealThumbnail() {
  await nextTick()
  const selected = strip.value?.querySelector('[aria-current="true"]')
  if (selected && strip.value) strip.value.scrollLeft = selected.offsetLeft - strip.value.clientWidth / 2 + selected.clientWidth / 2
}
function select(id, manual = true) {
  if (!props.images.some(image => image.id === id)) return
  if (manual) stop()
  if (activeId.value === id) { fit(); revealThumbnail(); return }
  activeId.value = id; resetImage(); revealThumbnail()
}
async function open(id, trigger = null) {
  if (!props.images.some(image => image.id === id)) return
  if (!locked) {
    returnFocus = trigger || document.activeElement
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'; locked = true
    document.addEventListener('fullscreenchange', syncFullscreen)
    document.addEventListener('visibilitychange', visibilityChanged)
  }
  select(id)
  await nextTick(); dialog.value?.focus()
}
function restore() {
  stop()
  if (!locked) return
  document.body.style.overflow = previousOverflow; locked = false
  document.removeEventListener('fullscreenchange', syncFullscreen)
  document.removeEventListener('visibilitychange', visibilityChanged)
  if (document.fullscreenElement === dialog.value) document.exitFullscreen?.().catch(() => {})
  fullscreen.value = false
}
function close() {
  restore(); activeId.value = null
  const target = returnFocus; returnFocus = null
  nextTick(() => { if (target?.isConnected) target.focus() })
}
function shift(direction, manual = true) {
  if (!active.value || props.images.length < 2) return
  const index = (activeIndex.value + direction + props.images.length) % props.images.length
  select(props.images[index].id, manual)
}
function changeZoom(delta) {
  const levels = [1, 1.5, 2, 3]
  const index = Math.max(0, levels.indexOf(zoom.value))
  zoom.value = levels[Math.min(levels.length - 1, Math.max(0, index + delta))]
  pan.value = { x: 0, y: 0 }; stop()
}
function fit() { zoom.value = 1; pan.value = { x: 0, y: 0 } }
function togglePlay() {
  if (playing.value) { stop(); return }
  if (props.images.length < 2) return
  fit(); playing.value = true
  timer = setInterval(() => { if (!imageLoading.value) shift(1, false) }, 4000)
}
function visibilityChanged() { if (document.hidden) stop() }
function syncFullscreen() { fullscreen.value = document.fullscreenElement === dialog.value }
async function toggleFullscreen() {
  try {
    if (document.fullscreenElement === dialog.value) await document.exitFullscreen()
    else await dialog.value?.requestFullscreen?.()
  } catch { /* The viewer already fills the browser viewport when fullscreen is unavailable. */ }
}
function onKeydown(event) {
  if (event.key === 'Escape') { event.preventDefault(); close(); return }
  if (event.key === 'ArrowLeft') { event.preventDefault(); shift(-1) }
  if (event.key === 'ArrowRight') { event.preventDefault(); shift(1) }
  if (event.key === 'Home') { event.preventDefault(); select(props.images[0].id) }
  if (event.key === 'End') { event.preventDefault(); select(props.images.at(-1).id) }
  if (event.key === '+' || event.key === '=') { event.preventDefault(); changeZoom(1) }
  if (event.key === '-') { event.preventDefault(); changeZoom(-1) }
  if (event.key === 'Tab') {
    const elements = [...dialog.value.querySelectorAll('button:not(:disabled),a[href]')].filter(element => element.getClientRects().length)
    const first = elements[0], last = elements.at(-1)
    if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.value)) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog.value)) { event.preventDefault(); first?.focus() }
  }
}
function pointerDown(event) {
  if (event.target?.closest?.('button,a')) return
  if (event.button != null && event.button !== 0) return
  pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, pan: { ...pan.value } }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}
function pointerMove(event) {
  if (!pointer || pointer.id !== event.pointerId || zoom.value === 1) return
  const maxX = (imageElement.value?.clientWidth || 0) * (zoom.value - 1) / 2
  const maxY = (imageElement.value?.clientHeight || 0) * (zoom.value - 1) / 2
  pan.value = { x: Math.max(-maxX, Math.min(maxX, pointer.pan.x + event.clientX - pointer.x)),
    y: Math.max(-maxY, Math.min(maxY, pointer.pan.y + event.clientY - pointer.y)) }
}
function pointerUp(event) {
  if (!pointer || pointer.id !== event.pointerId) return
  const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y
  pointer = null
  if (zoom.value === 1 && Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.4) shift(dx < 0 ? 1 : -1)
}
function retryImage() { imageError.value = false; imageLoading.value = true; retry.value++ }
watch(() => props.images, () => { if (activeId.value !== null && !active.value) close() })
onBeforeUnmount(restore)
defineExpose({ open, close })
</script>
<template>
  <section v-if="showGrid && images.length" class="photo-gallery" aria-label="Galeria zdjęć">
    <div class="gallery-toolbar"><div class="gallery-count"><Images :size="19" /><strong>Zdjęcia</strong><span>{{ images.length }}</span></div><div class="gallery-controls"><div class="gallery-view-switch" role="group" aria-label="Widok zdjęć"><button :aria-pressed="layout === 'grid'" aria-label="Siatka zdjęć" title="Siatka zdjęć" @click="setLayout('grid')"><Grid3X3 :size="17" /></button><button :aria-pressed="layout === 'list'" aria-label="Lista zdjęć" title="Lista zdjęć" @click="setLayout('list')"><List :size="18" /></button></div><div v-if="layout === 'grid'" class="gallery-sizes" role="group" aria-label="Rozmiar miniaturek"><button v-for="option in [{ value: 'small', label: 'Małe' }, { value: 'medium', label: 'Średnie' }, { value: 'large', label: 'Duże' }]" :key="option.value" :aria-pressed="thumbnailSize === option.value" @click="setSize(option.value)">{{ option.label }}</button></div></div></div>
    <div class="photo-grid" :class="[thumbnailSize, { 'photo-list': layout === 'list' }]"><button v-for="(image, index) in images" :key="image.id" class="photo-card" :aria-label="`Otwórz zdjęcie ${index + 1}: ${image.title}`" @click="open(image.id, $event.currentTarget)"><span class="photo-thumbnail"><img v-if="!failedThumbnails[image.id]" :src="image.src" :alt="image.title" loading="lazy" decoding="async" @error="failedThumbnails[image.id] = true" /><span v-else class="photo-unavailable"><ImageOff :size="30" />Podgląd niedostępny</span><span class="photo-enlarge"><Maximize :size="18" /></span></span><span class="photo-caption"><strong>{{ image.title }}</strong><small>{{ image.filename }}</small></span></button></div>
  </section>
  <Teleport to="body">
    <div v-if="active" ref="dialog" class="photo-lightbox" role="dialog" aria-modal="true" aria-labelledby="lightbox-title" tabindex="-1" @keydown.stop="onKeydown">
      <header class="lightbox-header"><div class="lightbox-heading"><span class="lightbox-counter" aria-live="polite">{{ activeIndex + 1 }} / {{ images.length }}</span><div><h2 id="lightbox-title">{{ active.title }}</h2><small>{{ active.filename }}</small></div></div><div class="lightbox-tools"><button :disabled="images.length < 2" :aria-label="playing ? 'Zatrzymaj pokaz slajdów' : 'Uruchom pokaz slajdów'" :title="playing ? 'Zatrzymaj pokaz' : 'Pokaz slajdów'" :aria-pressed="playing" @click="togglePlay"><Pause v-if="playing" :size="20" /><Play v-else :size="20" /></button><button :disabled="zoom <= 1 || imageError" aria-label="Pomniejsz zdjęcie" title="Pomniejsz (-)" @click="changeZoom(-1)"><ZoomOut :size="20" /></button><button :disabled="zoom >= 3 || imageError" aria-label="Powiększ zdjęcie" title="Powiększ (+)" @click="changeZoom(1)"><ZoomIn :size="20" /></button><button class="lightbox-fit" aria-label="Dopasuj zdjęcie" title="Dopasuj do ekranu" @click="fit">{{ Math.round(zoom * 100) }}%</button><button :aria-pressed="showThumbnails" aria-label="Pokaż lub ukryj miniatury" title="Miniatury" @click="showThumbnails = !showThumbnails; revealThumbnail()"><PanelBottom :size="20" /></button><button :aria-label="fullscreen ? 'Wyłącz pełny ekran' : 'Włącz pełny ekran'" title="Pełny ekran" @click="toggleFullscreen"><Minimize v-if="fullscreen" :size="20" /><Maximize v-else :size="20" /></button><a :href="active.download" aria-label="Pobierz zdjęcie" title="Pobierz zdjęcie"><Download :size="20" /></a><button class="lightbox-close" aria-label="Zamknij podgląd zdjęć" title="Zamknij (Esc)" @click="close"><X :size="23" /></button></div></header>
      <div class="lightbox-main"><button class="lightbox-arrow previous" :disabled="images.length < 2" aria-label="Poprzednie zdjęcie" title="Poprzednie zdjęcie (←)" @click="shift(-1)"><ChevronLeft :size="32" /></button>
        <div class="lightbox-stage" :class="{ zoomed: zoom > 1 }" @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="pointer = null" @dblclick="zoom === 1 ? changeZoom(1) : fit()">
          <p v-if="imageLoading && !imageError" class="lightbox-loading" role="status">Wczytywanie zdjęcia…</p>
          <div v-if="imageError" class="lightbox-image-error" role="alert"><ImageOff :size="38" /><strong>Nie udało się wczytać zdjęcia</strong><span>Link mógł wygasnąć albo plik jest niedostępny.</span><button @click.stop="retryImage"><RotateCcw :size="16" />Spróbuj ponownie</button></div>
          <img v-else :key="activeSource" ref="imageElement" class="lightbox-image" :src="activeSource" :alt="active.title" draggable="false" :style="{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, opacity: imageLoading ? 0 : 1 }" @load="imageLoading = false" @error="imageError = true; imageLoading = false; stop()" />
        </div>
        <button class="lightbox-arrow next" :disabled="images.length < 2" aria-label="Następne zdjęcie" title="Następne zdjęcie (→)" @click="shift(1)"><ChevronRight :size="32" /></button>
      </div>
      <footer class="lightbox-footer"><p class="lightbox-hint">{{ zoom > 1 ? 'Przeciągnij zdjęcie, aby przesunąć podgląd.' : 'Przewijaj strzałkami lub przesuń zdjęcie palcem.' }}</p><div v-if="showThumbnails" ref="strip" class="lightbox-thumbnails" aria-label="Miniatury zdjęć"><button v-for="(image, index) in images" :key="image.id" :aria-label="`Pokaż zdjęcie ${index + 1}: ${image.title}`" :aria-current="activeId === image.id ? 'true' : undefined" @click="select(image.id)"><img :src="image.src" :alt="image.title" loading="lazy" /><span>{{ index + 1 }}</span></button></div></footer>
    </div>
  </Teleport>
</template>
<style scoped>
.photo-gallery { margin:0 0 26px; }.gallery-toolbar,.gallery-count,.gallery-controls,.gallery-view-switch,.gallery-sizes { display:flex; align-items:center; gap:8px; }.gallery-toolbar { justify-content:space-between; flex-wrap:wrap; gap:14px; margin:0 0 16px; }.gallery-count { color:var(--secondary); font-size:13px; }.gallery-count>svg { color:var(--accent); }.gallery-count>span { padding:3px 7px; border-radius:6px; background:var(--accent-soft); color:var(--accent); font-size:11px; }.gallery-controls { flex-wrap:wrap; }.gallery-view-switch,.gallery-sizes { gap:3px; padding:3px; border:1px solid var(--border); border-radius:9px; background:var(--surface); }.gallery-controls button { display:grid; place-items:center; min-height:32px; padding:6px 9px; border:0; border-radius:6px; background:transparent; color:var(--muted); font-size:11px; }.gallery-controls button[aria-pressed=true] { color:var(--accent); background:var(--accent-soft); }.photo-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(min(240px,100%),1fr)); gap:16px; }.photo-grid.small { grid-template-columns:repeat(auto-fill,minmax(min(155px,100%),1fr)); gap:10px; }.photo-grid.large { grid-template-columns:repeat(auto-fill,minmax(min(350px,100%),1fr)); gap:20px; }.photo-card { display:flex; flex-direction:column; min-width:0; padding:0; overflow:hidden; border:1px solid var(--border); border-radius:13px; background:var(--surface); text-align:left; cursor:pointer; transition:box-shadow .15s,border-color .15s; }.photo-card:hover { border-color:var(--accent); box-shadow:0 6px 20px #1e183610; }.photo-thumbnail { display:block; position:relative; aspect-ratio:4/3; width:100%; overflow:hidden; background:var(--surface-soft); }.photo-thumbnail>img { display:block; width:100%; height:100%; object-fit:cover; }.photo-enlarge { position:absolute; right:10px; bottom:10px; display:grid; place-items:center; padding:7px; border-radius:8px; color:white; background:#131725a8; opacity:0; transition:opacity .15s; }.photo-card:hover .photo-enlarge,.photo-card:focus-visible .photo-enlarge { opacity:1; }.photo-caption { display:block; width:100%; min-width:0; box-sizing:border-box; padding:13px 14px; }.photo-caption strong,.photo-caption small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.photo-caption strong { font-size:12px; font-weight:600; color:var(--text); }.photo-caption small { margin-top:5px; font-size:10px; color:var(--muted); }.photo-grid.small .photo-caption { padding:10px; }.photo-unavailable { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; gap:10px; color:var(--muted); font-size:11px; }.photo-grid.photo-list { grid-template-columns:minmax(0,1fr); gap:8px; }.photo-list .photo-card { flex-direction:row; align-items:center; }.photo-list .photo-thumbnail { width:100px; flex-shrink:0; }.photo-list .photo-caption { flex:1; }.photo-lightbox { position:fixed; inset:0; z-index:1000; display:flex; flex-direction:column; height:100dvh; min-height:0; width:100%; outline:none; background:#0e1119; color:#f7f8fc; font-family:inherit; }.lightbox-header { display:flex; align-items:center; justify-content:space-between; flex-shrink:0; gap:18px; padding:18px 24px; background:#171b25; border-bottom:1px solid #ffffff14; }.lightbox-heading { display:flex; align-items:center; gap:14px; min-width:0; }.lightbox-heading>div { min-width:0; }.lightbox-heading h2 { margin:0; font-size:15px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#f7f8fc; }.lightbox-heading small { display:block; margin-top:5px; color:#a4adbf; font-size:11px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.lightbox-counter { color:#bac6e3; font-size:12px; padding:7px 10px; border:1px solid #ffffff22; border-radius:8px; white-space:nowrap; }.lightbox-tools { display:flex; align-items:center; gap:5px; flex-shrink:0; }.photo-lightbox button,.photo-lightbox a { display:inline-flex; align-items:center; justify-content:center; gap:7px; border:1px solid transparent; border-radius:8px; background:transparent; color:#e5eaf6; padding:9px; text-decoration:none; cursor:pointer; font:inherit; }.photo-lightbox button:hover,.photo-lightbox a:hover { background:#ffffff13; }.photo-lightbox button:focus-visible,.photo-lightbox a:focus-visible { outline:2px solid #b49bff; outline-offset:2px; }.photo-lightbox button:disabled { opacity:.3; cursor:default; }.photo-lightbox button[aria-pressed=true] { background:#9d7af433; color:#dbcaff; }.photo-lightbox .lightbox-fit { font-size:11px; min-width:50px; }.photo-lightbox .lightbox-close { margin-left:8px; background:#ffffff0b; }.lightbox-main { position:relative; display:flex; flex:1; min-height:0; align-items:stretch; }.lightbox-stage { position:relative; display:flex; align-items:center; justify-content:center; flex:1; min-width:0; min-height:0; overflow:hidden; touch-action:pan-y; user-select:none; padding:16px 0; }.lightbox-stage.zoomed { cursor:grab; touch-action:none; }.lightbox-stage.zoomed:active { cursor:grabbing; }.lightbox-image { display:block; max-width:100%; max-height:100%; object-fit:contain; flex-shrink:0; transition:opacity .15s; }.lightbox-main .lightbox-arrow { width:68px; flex:0 0 68px; border-radius:0; padding:10px; }.lightbox-loading { position:absolute; color:#b8c1d5; font-size:12px; }.lightbox-image-error { display:flex; flex-direction:column; align-items:center; text-align:center; padding:25px; gap:14px; color:#b8c1d5; }.lightbox-image-error strong { color:white; font-size:16px; }.lightbox-image-error span { font-size:12px; line-height:1.6; }.lightbox-image-error button { border-color:#ffffff44; font-size:12px; }.lightbox-footer { flex-shrink:0; padding:10px 24px 16px; background:#171b25; border-top:1px solid #ffffff14; }.lightbox-hint { text-align:center; font-size:10px; color:#a4adbf; margin:0 0 10px; }.lightbox-thumbnails { display:flex; justify-content:flex-start; gap:9px; overflow-x:auto; padding:5px; position:relative; max-width:1100px; margin:0 auto; scrollbar-width:thin; scrollbar-color:#626a7c transparent; }.photo-lightbox .lightbox-thumbnails button { position:relative; flex:0 0 88px; width:88px; height:62px; padding:0; overflow:hidden; border:2px solid transparent; opacity:.55; }.photo-lightbox .lightbox-thumbnails button[aria-current=true] { opacity:1; border-color:#baa0ff; box-shadow:0 0 0 2px #baa0ff28; }.lightbox-thumbnails img { width:100%; height:100%; object-fit:cover; }.lightbox-thumbnails span { position:absolute; right:3px; bottom:3px; padding:2px 4px; font-size:9px; border-radius:3px; background:#0e1119b3; color:white; }
@media(max-width:800px) { .lightbox-header { align-items:flex-start; padding:12px; gap:10px; flex-wrap:wrap; }.lightbox-heading { flex:1; }.lightbox-tools { gap:2px; }.photo-lightbox .lightbox-tools button,.photo-lightbox .lightbox-tools a { padding:7px; }.lightbox-main .lightbox-arrow { width:44px; flex-basis:44px; padding:4px; }.lightbox-footer { padding:9px 12px 12px; }.lightbox-thumbnails button { flex-basis:72px; width:72px; height:52px; } }
@media(max-width:520px) { .gallery-toolbar { align-items:flex-start; }.gallery-controls { gap:6px; }.photo-grid { grid-template-columns:minmax(0,1fr); }.photo-grid.small { grid-template-columns:repeat(2,minmax(0,1fr)); }.lightbox-heading { width:100%; flex-basis:100%; padding-right:44px; }.lightbox-tools { justify-content:center; width:100%; }.photo-lightbox .lightbox-close { position:absolute; top:10px; right:10px; margin:0; }.lightbox-main .lightbox-arrow { position:absolute; top:50%; transform:translateY(-50%); z-index:2; height:48px; width:38px; border-radius:7px; background:#171b2599; }.lightbox-arrow.previous { left:6px; }.lightbox-arrow.next { right:6px; }.lightbox-stage { padding:10px; }.lightbox-hint { font-size:9px; }.lightbox-counter { padding:6px 8px; }.lightbox-heading h2 { font-size:13px; } }
@media(prefers-reduced-motion:reduce) { .photo-card,.photo-enlarge,.lightbox-image { transition:none; } }
</style>
