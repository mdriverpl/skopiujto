import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const source = compileScript(parse(readFileSync(new URL('./PhotoUpload.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'upload-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function uploader(api) {
  const events = [], context = { computed, ref, nextTick() {}, onMounted() {}, onBeforeUnmount() {},
    FormData: class { values = new Map(); append(key, value) { this.values.set(key, value) } get(key) { return this.values.get(key) } } }
  for (const icon of ['Upload', 'ImagePlus', 'X', 'Check', 'AlertCircle']) context[icon] = {}
  runInNewContext(source, context)
  const state = context.component.setup({ api, endpoint: '/public-shares/token/photos', folderId: 'child' },
    { expose() {}, emit: (...event) => events.push(event) })
  return { state, events }
}
const file = (name = 'photo.png', size = 1024) => ({ name, size })

test('selection and dropping validate size and format before any request', async () => {
  const { state } = uploader(() => assert.fail('selection must not upload'))
  state.add([file('script.html'), file('big.jpg', 10485761), file('empty.png', 0), file('good.JPG')])
  assert.equal(state.queue.value.length, 4); assert.equal(state.pending.value.length, 1)
  assert.equal(state.pending.value[0].file.name, 'good.JPG')
  state.drop({ dataTransfer: { files: [file('dropped.webp')] } })
  assert.equal(state.pending.value.length, 2)
})

test('batch upload preserves failures and retry never resends successful photos', async () => {
  const calls = []; let fail = true
  const { state, events } = uploader(async (endpoint, method, body) => {
    const name = body.get('file').name; calls.push({ endpoint, method, folder: body.get('folder_id'), name })
    if (name === 'two.jpg' && fail) throw new Error('Network unavailable')
    return { id: name, image: true }
  })
  state.add([file('one.jpg'), file('two.jpg')]); await state.upload()
  assert.equal(state.completed.value, 1); assert.equal(state.pending.value[0].error, 'Network unavailable')
  fail = false; await state.upload()
  assert.deepEqual(calls.map(item => item.name), ['one.jpg', 'two.jpg', 'two.jpg'])
  assert.ok(calls.every(item => item.folder === 'child' && item.method === 'POST'))
  assert.equal(events.filter(item => item[0] === 'uploaded').length, 2)
  assert.equal(state.completed.value, 2)
})

test('pending upload blocks duplicate starts, closing and removing queued photos', async () => {
  let resolve; let calls = 0
  const { state, events } = uploader(() => { calls++; return new Promise(done => { resolve = done }) })
  state.add([file()]); const pending = state.upload()
  await state.upload(); state.close(); state.remove(state.queue.value[0].id); state.add([file('ignored.png')])
  assert.equal(calls, 1); assert.equal(events.length, 0); assert.equal(state.queue.value.length, 1)
  resolve({ id: 'new', image: true }); await pending
  assert.equal(state.busy.value, false); state.close(); assert.equal(events.at(-1)[0], 'close')
})
