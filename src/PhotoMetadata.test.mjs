import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
const source = compileScript(parse(readFileSync(new URL('./PhotoMetadata.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'metadata-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(load) {
  const cleanups = [], context = { computed, ref, onMounted() {}, onBeforeUnmount: callback => cleanups.push(callback), Info: {}, X: {}, MapPin: {}, RotateCcw: {} }
  runInNewContext(source, context)
  const state = context.component.setup({ photo: { id: 'one', filename: 'photo.jpg', file_size: 1048576 }, load }, { expose() {}, emit() {} })
  return { state, unmount: () => cleanups.forEach(callback => callback()) }
}
test('metadata shows real file geometry, size and zero-valued GPS coordinates', async () => {
  const { state } = panel(async () => ({ width: 1200, height: 800, format: 'JPEG', mode: 'RGB', tags: [], location: { latitude: 0, longitude: 0 } }))
  await state.read()
  assert.equal(state.rows.value.find(([label]) => label === 'Wymiary')[1], '1200 × 800 px')
  assert.equal(state.rows.value.find(([label]) => label === 'Rozmiar pliku')[1], '1.00 MB')
  assert.equal(state.coordinates.value, '0.000000, 0.000000')
})
test('a failed metadata request keeps file details and can be retried', async () => {
  let fail = true
  const { state } = panel(async () => { if (fail) throw new Error('Unavailable'); return { width: 12, height: 16, tags: [], location: null } })
  await state.read(); assert.equal(state.error.value, 'Unavailable'); assert.equal(state.rows.value[0][1], 'photo.jpg')
  fail = false; await state.read(); assert.equal(state.error.value, ''); assert.equal(state.coordinates.value, null)
})
test('responses for a closed or superseded metadata panel cannot overwrite the current photo', async () => {
  const callbacks = []
  const { state, unmount } = panel(() => new Promise(resolve => callbacks.push(resolve)))
  const first = state.read(), second = state.read()
  callbacks[1]({ width: 20, height: 30 }); await second
  callbacks[0]({ width: 10, height: 15 }); await first
  assert.equal(state.data.value.width, 20)
  const third = state.read(); unmount(); callbacks[2]({ width: 999 }); await third
  assert.equal(state.data.value, null)
})
