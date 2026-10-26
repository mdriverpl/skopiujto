import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, nextTick, reactive, ref, watch } from 'vue'

const source = compileScript(parse(readFileSync(new URL('./PhotoGallery.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'gallery-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
const images = [1, 2, 3].map(id => ({ id: String(id), title: `Photo ${id}`, src: `/photo/${id}`, download: `/download/${id}` }))
function gallery() {
  const cleanup = [], focus = []
  const trigger = { isConnected: true, focus() { focus.push('trigger') } }
  const document = { activeElement: trigger, body: { style: { overflow: 'auto' } },
    addEventListener() {}, removeEventListener() {}, fullscreenElement: null }
  const context = { computed, nextTick, reactive, ref, watch, document, setInterval, clearInterval,
    onBeforeUnmount: callback => cleanup.push(callback) }
  for (const icon of ['Images', 'Grid3X3', 'List', 'ChevronLeft', 'ChevronRight', 'X', 'Download', 'ZoomIn', 'ZoomOut',
    'Maximize', 'Minimize', 'Play', 'Pause', 'PanelBottom', 'RotateCcw', 'ImageOff']) context[icon] = {}
  runInNewContext(source, context)
  const props = reactive({ images: images.map(image => ({ ...image })), showGrid: true })
  const state = context.component.setup(props, { expose() {} })
  state.dialog.value = { focus() { focus.push('viewer') } }
  return { state, props, document, focus, unmount: () => cleanup.forEach(callback => callback()) }
}

test('next, previous, thumbnail selection and keyboard shortcuts browse the full image sequence', async () => {
  const { state, unmount } = gallery()
  await state.open('2')
  assert.equal(state.active.value.id, '2')
  state.shift(1); assert.equal(state.active.value.id, '3')
  state.shift(1); assert.equal(state.active.value.id, '1')
  state.shift(-1); assert.equal(state.active.value.id, '3')
  state.select('1'); assert.equal(state.activeIndex.value, 0)
  state.onKeydown({ key: 'ArrowRight', preventDefault() {} }); assert.equal(state.active.value.id, '2')
  state.onKeydown({ key: 'End', preventDefault() {} }); assert.equal(state.active.value.id, '3')
  state.onKeydown({ key: 'Home', preventDefault() {} }); assert.equal(state.active.value.id, '1')
  unmount()
})

test('zoom resets between images and selecting the current thumbnail does not leave a cached image loading', async () => {
  const { state, unmount } = gallery()
  await state.open('1')
  state.imageLoading.value = false
  state.changeZoom(1); assert.equal(state.zoom.value, 1.5)
  state.select('1')
  assert.equal(state.zoom.value, 1)
  assert.equal(state.imageLoading.value, false)
  state.changeZoom(1); state.shift(1)
  assert.equal(state.zoom.value, 1)
  assert.equal(state.pan.value.x, 0)
  unmount()
})

test('horizontal swipes navigate while vertical gestures and taps keep the current photo', async () => {
  const { state, unmount } = gallery()
  await state.open('2')
  const down = { button: 0, pointerId: 1, clientX: 200, clientY: 100, currentTarget: {} }
  state.pointerDown(down); state.pointerUp({ pointerId: 1, clientX: 100, clientY: 110 })
  assert.equal(state.active.value.id, '3')
  state.pointerDown(down); state.pointerUp({ pointerId: 1, clientX: 300, clientY: 105 })
  assert.equal(state.active.value.id, '2')
  state.pointerDown(down); state.pointerUp({ pointerId: 1, clientX: 205, clientY: 200 })
  assert.equal(state.active.value.id, '2')
  state.pointerDown(down); state.pointerUp({ pointerId: 1, clientX: 201, clientY: 101 })
  assert.equal(state.active.value.id, '2')
  unmount()
})

test('Escape and removal of the viewed photo release page scrolling and stop the slideshow', async () => {
  const { state, props, document, focus, unmount } = gallery()
  await state.open('1')
  assert.equal(document.body.style.overflow, 'hidden')
  state.togglePlay(); assert.equal(state.playing.value, true)
  state.onKeydown({ key: 'Escape', preventDefault() {} })
  await nextTick()
  assert.equal(state.active.value, null)
  assert.equal(state.playing.value, false)
  assert.equal(document.body.style.overflow, 'auto')
  assert.equal(focus.at(-1), 'trigger')
  await state.open('2')
  props.images = props.images.filter(image => image.id !== '2')
  await nextTick()
  assert.equal(state.active.value, null)
  assert.equal(document.body.style.overflow, 'auto')
  unmount()
})
