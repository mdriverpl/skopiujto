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
  const context = { computed, nextTick, reactive, ref, watch, document, setInterval, clearInterval, URLSearchParams,
    onBeforeUnmount: callback => cleanup.push(callback) }
  for (const icon of ['Images', 'Grid3X3', 'List', 'ChevronLeft', 'ChevronRight', 'X', 'Download', 'ZoomIn', 'ZoomOut',
    'Maximize', 'Minimize', 'Play', 'Pause', 'PanelBottom', 'RotateCcw', 'ImageOff', 'MapPin', 'ExternalLink', 'Heart', 'MessageSquare', 'Share2', 'Info', 'PhotoActivity', 'PhotoLike', 'PhotoMetadata']) context[icon] = {}
  runInNewContext(source, context)
  const props = reactive({ images: images.map(image => ({ ...image })), showGrid: true })
  const state = context.component.setup(props, { expose() {}, emit() {} })
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

test('metadata opens with the photo and a successful retry restores the map for the same file only', async () => {
  const { state, unmount } = gallery()
  await state.open('1'); assert.equal(state.showMetadata.value, true)
  state.metadataLoaded({ id: '2', location: { latitude: 1, longitude: 2 } })
  assert.equal(state.location.value, null)
  state.metadataLoaded({ id: '1', location: { latitude: 0, longitude: 0 } })
  state.openMap(); assert.equal(state.showMap.value, true); assert.equal(state.showMetadata.value, false)
  state.toggleMetadata(); assert.equal(state.showMetadata.value, true); assert.equal(state.showMap.value, false)
  state.toggleActivity(); assert.equal(state.showMetadata.value, false)
  unmount()
})

test('typing and cursor keys in photo forms do not navigate or zoom the photo', async () => {
  const { state, unmount } = gallery()
  await state.open('2')
  for (const key of ['ArrowLeft', 'ArrowRight', 'Home', 'End', '+', '-', 'Escape']) {
    state.onKeydown({ key, target: { closest: () => ({}) }, preventDefault() { assert.fail('editing must keep native input keys') } })
    assert.equal(state.active.value.id, '2'); assert.equal(state.zoom.value, 1)
  }
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

test('GPS map appears only for valid image metadata and late responses cannot attach a previous photo location', async () => {
  const { state, props, unmount } = gallery()
  let resolveFirst
  props.loadLocation = image => image.id === '1' ? new Promise(resolve => { resolveFirst = resolve })
    : Promise.resolve({ location: { latitude: 0, longitude: 0 } })
  await state.open('1')
  assert.equal(state.location.value, null)
  state.select('2')
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.location.value.latitude, 0)
  resolveFirst({ location: { latitude: 52.23, longitude: 21.01 } })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.location.value.latitude, 0)
  assert.match(state.mapSource.value, /^https:\/\/www.openstreetmap.org\/export\/embed.html\?/)
  assert.equal(new URL(state.mapSource.value).searchParams.get('marker'), '0,0')
  state.close()
  assert.equal(state.location.value, null)
  unmount()
})

test('missing, invalid or unavailable GPS data never invents a map location', async () => {
  const { state, props, unmount } = gallery()
  props.loadLocation = image => image.id === '1' ? Promise.resolve({ location: null })
    : image.id === '2' ? Promise.resolve({ location: { latitude: 95, longitude: 21 } }) : Promise.reject(new Error('Metadata unavailable'))
  for (const id of ['1', '2', '3']) {
    await state.open(id)
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(state.location.value, null)
    assert.equal(state.mapSource.value, '')
  }
  unmount()
})
