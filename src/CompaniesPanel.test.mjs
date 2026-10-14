import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./CompaniesPanel.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'companies-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { computed, ref, onMounted() {}, window: { confirm: () => true } }
  runInNewContext(compiled, context)
  return context.component.setup({ api }, { expose() {} })
}
test('company edit sends original version and preserves draft after conflict', async () => {
  let sent
  const state = panel(async (path, method, body) => { sent = { path, method, body }; throw new Error('Konflikt wersji') })
  state.edit({ id: 'firm', name: 'Firma', nip: '', address: '', email: '', phone: '', version: 3 })
  state.draft.value.name = 'Nowa nazwa'
  await state.save()
  assert.equal(sent.path, '/admin/companies/firm')
  assert.equal(sent.method, 'PATCH')
  assert.equal(sent.body.version, 3)
  assert.equal(state.draft.value.name, 'Nowa nazwa')
  assert.equal(state.busy.value, false)
})
test('new company is explicitly saved and search includes registration data', async () => {
  const calls = [], saved = { id: 'firm', name: 'Firma', nip: '12345', email: '', address: '', phone: '', user_count: 0 }
  const state = panel(async (path, method, body) => { calls.push({ path, method, body }); return method ? saved : [saved] })
  state.edit()
  assert.equal(calls.length, 0)
  state.draft.value.name = 'Firma'
  state.draft.value.nip = '12345'
  await state.save()
  assert.equal(calls[0].method, 'POST')
  assert.equal(state.draft.value, null)
  state.search.value = '12345'
  assert.equal(state.filtered.value.length, 1)
  state.search.value = 'missing'
  assert.equal(state.filtered.value.length, 0)
})
