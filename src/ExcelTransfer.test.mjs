import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./ExcelTransfer.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'excel-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { ref, FormData }, events = []
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, dictionary: { id: 'one', name: 'Pracownicy' } }, { expose() {}, emit: (...args) => events.push(args) })
  return { state, events }
}
const file = new File(['excel'], 'data.xlsx')
const preview = { fields: ['Imię'], rows: [{ 'Imię': 'Anna' }], count: 1, version: 2, sheet: 'Dane' }
test('upload previews before commit and imports with the preview schema version', async () => {
  const calls = []
  const { state, events } = panel(async (path, method, body) => { calls.push({ path, method, body }); return path.endsWith('preview') ? preview : { imported: 1 } })
  await state.choose(file)
  assert.equal(calls.length, 1); assert.ok(calls[0].body instanceof FormData)
  assert.equal(events.length, 0)
  await state.commit()
  assert.equal(calls[1].path, '/dictionaries/one/excel/import')
  assert.equal(calls[1].body.version, 2)
  assert.equal(calls[1].body.rows[0]['Imię'], 'Anna')
  assert.equal(events[0][0], 'imported'); assert.equal(state.preview.value, null)
})
test('unsupported uploads are blocked and failures retain a preview for retry', async () => {
  let calls = 0
  const { state } = panel(async () => { calls++; throw new Error('Pola słownika zmieniły się') })
  await state.choose(new File(['old'], 'data.xls')); assert.equal(calls, 0)
  state.preview.value = preview; await state.commit()
  assert.equal(state.preview.value.count, 1)
  assert.equal(state.busy.value, false)
  assert.equal(state.error.value, 'Pola słownika zmieniły się')
})
test('busy imports cannot be submitted twice', async () => {
  let complete, calls = 0
  const { state } = panel(() => { calls++; return new Promise(resolve => { complete = resolve }) })
  state.preview.value = preview
  const first = state.commit(); await state.commit(); assert.equal(calls, 1)
  complete({ imported: 1 }); await first
})
