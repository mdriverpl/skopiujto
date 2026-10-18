import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./EDeliverySettings.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'connection-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function settings(api, initial = {}) {
  const events = [], mounted = [], context = { ref, onMounted: callback => mounted.push(callback), window: { confirm: () => true } }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, initial }, { expose() {}, emit: (...args) => events.push(args) })
  state.mount = async () => { for (const callback of mounted) await callback() }
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

test('standalone page loads account configuration and keeps stored credentials blank', async () => {
  const calls = []
  const { state } = settings(async (path, method) => {
    calls.push([path, method])
    return { enabled: true, address: 'AE:PL-test', system_name: 'Portal', version: 4, has_certificate: true, has_private_key: true }
  }, null)
  await state.save()
  assert.equal(calls.length, 0)
  await state.mount()
  assert.deepEqual(calls, [['/edeliveries/connection', undefined]])
  assert.equal(state.loaded.value, true)
  assert.equal(state.form.value.address, 'AE:PL-test')
  assert.equal(state.form.value.version, 4)
  assert.equal(state.form.value.has_private_key, true)
  assert.equal(state.form.value.private_key, '')
  assert.equal(state.form.value.certificate, '')
})

test('failed initial load prevents overwriting configuration and can be retried', async () => {
  let fail = true
  const calls = []
  const { state } = settings(async (path, method) => {
    calls.push([path, method])
    if (fail) throw new Error('Brak połączenia')
    return { enabled: true, address: 'AE:PL-test', version: 2 }
  }, null)
  await state.mount()
  await state.save()
  await state.disconnect()
  assert.equal(calls.length, 1)
  assert.equal(state.loaded.value, false)
  assert.match(state.error.value, /Brak połączenia/)
  fail = false
  await state.load()
  assert.equal(state.loaded.value, true)
  assert.equal(state.form.value.version, 2)
  assert.equal(state.error.value, '')
})

test('disconnect clears the configuration and secret fields while keeping the settings page open', async () => {
  const calls = []
  const { state, events } = settings(async (path, method) => { calls.push([path, method]); return {} }, { enabled: true, version: 3 })
  state.form.value.private_key = 'unsaved-key'
  state.form.value.certificate = 'unsaved-certificate'
  state.form.value.key_password = 'password'
  await state.disconnect()
  assert.deepEqual(calls, [['/edeliveries/connection', 'DELETE']])
  assert.equal(state.form.value.enabled, false)
  assert.equal(state.form.value.version, 0)
  assert.equal(state.form.value.private_key, '')
  assert.equal(state.form.value.certificate, '')
  assert.equal(state.form.value.key_password, '')
  assert.match(state.notice.value, /odłączona/)
  assert.equal(events.some(event => event[0] === 'close'), false)
})
