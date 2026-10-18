import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { parse, compileScript } from '@vue/compiler-sfc'
import { ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./MailSettings.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'settings-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api, initial) {
  const mounted = [], context = { ref, onMounted: callback => mounted.push(callback) }, events = []
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, initial }, { expose() {}, emit: (...args) => events.push(args) })
  state.mount = async () => { for (const callback of mounted) await callback() }
  return { state, events }
}
const initial = { account: { email: 'jan@example.com', sender_name: 'Jan', version: 1,
  smtp: { enabled: true, host: 'smtp.example.com', port: 465, security: 'ssl', username: 'jan@example.com', has_password: true },
  imap: { enabled: false, host: '', port: 993, security: 'ssl', username: '', has_password: false } } }

test('standalone settings page loads saved account before allowing changes', async () => {
  const calls = []
  const { state } = panel(async (path, method) => { calls.push([path, method]); return initial })
  await state.save()
  assert.equal(calls.length, 0)
  await state.mount()
  assert.deepEqual(calls, [['/client-mail/settings', undefined]])
  assert.equal(state.loaded.value, true)
  assert.equal(state.form.value.email, 'jan@example.com')
  assert.equal(state.form.value.version, 1)
  assert.equal(state.form.value.smtp.password, '')
})

test('failed initial load cannot overwrite account and retry restores saved configuration', async () => {
  let fail = true
  const calls = []
  const { state } = panel(async (path, method) => {
    calls.push([path, method])
    if (fail) throw new Error('Brak połączenia')
    return initial
  })
  await state.mount()
  assert.equal(state.loaded.value, false)
  assert.match(state.error.value, /Brak połączenia/)
  await state.save()
  assert.equal(calls.length, 1)
  fail = false
  await state.load()
  assert.equal(state.loaded.value, true)
  assert.equal(state.error.value, '')
  assert.equal(state.form.value.smtp.host, 'smtp.example.com')
})

test('saved passwords stay blank and save uses latest version without returning secrets', async () => {
  let body
  const { state, events } = panel(async (path, method, payload) => {
    body = payload; return { account: { ...initial.account, version: 2 } }
  }, initial)
  assert.equal(state.form.value.smtp.password, '')
  state.form.value.smtp.password = 'new-secret'
  await state.save()
  assert.equal(body.version, 1)
  assert.equal(body.smtp.password, 'new-secret')
  assert.equal(state.form.value.smtp.password, '')
  assert.equal(state.form.value.version, 2)
  assert.equal(events[0][0], 'saved')
})

test('save failure preserves all entered fields and does not test connection', async () => {
  const calls = []
  const { state } = panel(async path => { calls.push(path); throw new Error('Nie udało się zapisać') }, initial)
  state.form.value.smtp.password = 'secret'
  await state.save('smtp')
  assert.equal(calls.length, 1)
  assert.equal(state.form.value.smtp.password, 'secret')
  assert.equal(state.busy.value, false)
  assert.match(state.error.value, /zapisać/)
})

test('test connection saves first and security selects standard ports', async () => {
  const calls = []
  const { state } = panel(async (path, method) => {
    calls.push([path, method]); return method === 'PUT' ? { account: initial.account } : { message: 'Połączenie działa.' }
  }, initial)
  state.form.value.smtp.security = 'starttls'; state.securityChanged('smtp')
  assert.equal(state.form.value.smtp.port, 587)
  state.form.value.imap.security = 'starttls'; state.securityChanged('imap')
  assert.equal(state.form.value.imap.port, 143)
  await state.save('imap')
  assert.deepEqual(calls, [['/client-mail/settings', 'PUT'], ['/client-mail/settings/test/imap', 'POST']])
  assert.equal(state.notice.value, 'Połączenie działa.')
})
