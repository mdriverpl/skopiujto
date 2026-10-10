import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { ref } from 'vue'

function component(api) {
  const code = compileScript(parse(readFileSync(new URL('./PasswordChange.vue', import.meta.url), 'utf8')).descriptor,
    { id: 'password-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
  const context = { ref, X: {} }, events = []
  runInNewContext(code, context)
  const state = context.component.setup({ api, required: false }, { expose() {}, emit: (...args) => events.push(args) })
  state.currentPassword.value = 'temporary-password'
  state.newPassword.value = 'replacement-password'
  state.confirmation.value = 'replacement-password'
  return { state, events }
}

test('mismatched confirmation prevents changing the password', async () => {
  let calls = 0
  const { state } = component(async () => { calls++ })
  state.confirmation.value = 'different-password'
  await state.save()
  assert.equal(calls, 0)
  assert.ok(state.error.value)
})

test('successful change sends credentials, clears fields and reports the account', async () => {
  const calls = [], account = { id: 'user', must_change_password: false }
  const { state, events } = component(async (...args) => { calls.push(args); return account })
  await state.save()
  assert.equal(calls[0][0], '/me/password')
  assert.equal(calls[0][1], 'POST')
  assert.equal(calls[0][2].current_password, 'temporary-password')
  assert.equal(calls[0][2].new_password, 'replacement-password')
  assert.deepEqual(events, [['saved', account]])
  assert.equal(state.currentPassword.value, '')
  assert.equal(state.newPassword.value, '')
  assert.equal(state.confirmation.value, '')
})

test('pending change blocks duplicate submission and failure allows correction', async () => {
  let reject, calls = 0
  const { state, events } = component(() => { calls++; return new Promise((_resolve, fail) => { reject = fail }) })
  const pending = state.save()
  await state.save()
  assert.equal(calls, 1)
  reject(new Error('Obecne hasło jest nieprawidłowe.'))
  await pending
  assert.equal(state.busy.value, false)
  assert.equal(state.currentPassword.value, 'temporary-password')
  assert.equal(events.length, 0)
  assert.ok(state.error.value)
})
