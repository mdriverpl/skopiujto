import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./ResourceHistory.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'history-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { ref, onMounted() {} }
  runInNewContext(compiled, context)
  return context.component.setup({ api, resource: { kind: 'document', id: 'my-document' } }, { expose() {}, emit() {} })
}
test('history loads older changes without replacing newer entries', async () => {
  const paths = []
  const state = panel(async path => { paths.push(path); return path.includes('?') ? { items: [{ id: 1 }], next_before: null } : { items: [{ id: 2 }], next_before: 2 } })
  await state.load(); await state.load(true); await state.load(true)
  assert.equal(paths[0], '/history/document/my-document')
  assert.equal(paths[1], '/history/document/my-document?before=2')
  assert.equal(paths.length, 2); assert.equal(state.items.value.length, 2); assert.equal(state.items.value[0].id, 2)
})
test('failed refresh preserves already loaded history and displays error', async () => {
  const state = panel(async () => { throw Error('Brak dostępu') })
  state.items.value = [{ id: 2 }]
  await state.load()
  assert.equal(state.error.value, 'Brak dostępu'); assert.equal(state.items.value.length, 1); assert.equal(state.busy.value, false)
})
