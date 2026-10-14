import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./EDeliverySettings.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'connection-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function settings(api, initial = {}) {
  const events = [], context = { ref, onMounted() {}, window: { confirm: () => true } }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, initial }, { expose() {}, emit: (...args) => events.push(args) })
  return { state, events }
}
test('save clears secret fields and sends test only after successful persistence', async () => {
  const calls = []
  const { state } = settings(async (path, method, body) => { calls.push({ path, method, body }); return path.endsWith('/test') ? { message: 'Połączenie działa' } : { enabled: true, version: 1, has_private_key: true } })
  state.form.value.enabled = true; state.form.value.private_key = 'test-private'; state.form.value.certificate = 'test-cert'
  await state.save(true)
  assert.equal(calls[0].method, 'PUT')
  assert.equal(calls[0].body.private_key, 'test-private')
  assert.equal(calls[1].path, '/edeliveries/connection/test')
  assert.equal(state.form.value.private_key, '')
  assert.equal(state.form.value.certificate, '')
  assert.equal(state.notice.value, 'Połączenie działa')
})
test('failed save preserves entered material and never calls connection test', async () => {
  let calls = 0
  const { state } = settings(async () => { calls++; throw new Error('Konflikt') })
  state.form.value.private_key = 'test-private'
  await state.save(true)
  assert.equal(calls, 1)
  assert.equal(state.form.value.private_key, 'test-private')
  assert.equal(state.error.value, 'Konflikt')
  assert.equal(state.busy.value, false)
})
test('blank existing secret fields preserve stored material and password', async () => {
  let body
  const { state } = settings(async (_path, _method, value) => { body = value; return { enabled: false, version: 3 } }, { has_private_key: true, has_certificate: true, version: 2 })
  await state.save()
  assert.equal(body.private_key, null)
  assert.equal(body.certificate, null)
  assert.equal(body.key_password, null)
  assert.equal(body.version, 2)
})
