import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

function component(filename, props) {
  const code = compileScript(parse(readFileSync(new URL(filename, import.meta.url), 'utf8')).descriptor,
    { id: 'channels-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
  const mounted = [], events = [], unmounted = [], context = {
    computed, ref, onMounted: callback => mounted.push(callback), onBeforeUnmount: callback => unmounted.push(callback),
    setInterval() { return 1 }, clearInterval() {}, document: { addEventListener() {}, removeEventListener() {} },
    window: { confirm: () => true },
  }
  for (const icon of ['X', 'CheckCircle2', 'Clock3', 'CircleAlert', 'RefreshCw']) context[icon] = {}
  runInNewContext(code, context)
  const state = context.component.setup(props, { expose() {}, emit: (...args) => events.push(args) })
  return { state, events, mount: () => mounted[0](), destroy: () => unmounted.forEach(callback => callback()) }
}
const file = { id: 'doc-one', version: 3, filename: 'file.txt', permissions: { send: true } }
const configured = { user: { configured: true }, email: { configured: true }, sms: { configured: true } }

test('choosing a user works without SMTP; only selected unavailable channels block sending', async () => {
  const { state, mount } = component('./FileEmailDialog.vue', { file, api: async path =>
    path === '/approval-settings' ? { ...configured, email: { configured: false, message: 'Brak SMTP' } }
      : path === '/sharing-options' ? { users: [{ id: 'reader', name: 'Anna' }] } : [] })
  await mount()
  assert.equal(state.canSend.value, false)
  state.recipients.value[0].channel = 'user'; state.changeChannel(state.recipients.value[0])
  assert.equal(state.canSend.value, true)
  assert.equal(state.users.value[0].name, 'Anna')
})

test('mixed send builds separate channel addresses and uses unified approval history', async () => {
  const calls = []
  const { state, events } = component('./FileEmailDialog.vue', { file, api: async (path, method, body) => {
    calls.push({ path, method, body })
    return { mailing_id: 'batch', history: [{ id: 'batch', recipients: body.recipients.map(person => ({ ...person, delivery_status: 'sent' })) }] }
  } })
  state.settings.value = configured
  state.recipients.value = [
    { channel: 'email', email: ' anna@example.com ', name: 'Anna', phone: 'stale', user_id: '' },
    { channel: 'sms', phone: ' +48 600 123 456 ', name: '', email: 'stale', user_id: '' },
    { channel: 'user', user_id: 'reader', name: '', phone: '', email: '' },
  ]
  await state.send()
  assert.equal(calls[0].path, '/documents/doc-one/emails')
  assert.equal(calls[0].body.version, 3)
  assert.equal(calls[0].body.recipients[0].email, 'anna@example.com')
  assert.equal('phone' in calls[0].body.recipients[0], false)
  assert.equal(calls[0].body.recipients[1].phone, '+48 600 123 456')
  assert.equal('email' in calls[0].body.recipients[1], false)
  assert.equal(calls[0].body.recipients[2].user_id, 'reader')
  assert.equal(state.tab.value, 'history')
  assert.ok(events.some(event => event[0] === 'updated'))
})

test('pending send blocks duplicate submission and a failure preserves entered recipients', async () => {
  let fail, calls = 0
  const { state } = component('./FileEmailDialog.vue', { file, api: (path, method) => {
    if (!method) return Promise.resolve([])
    calls++; return new Promise((_resolve, reject) => { fail = reject })
  } })
  state.settings.value = configured
  state.recipients.value[0].email = 'anna@example.com'
  const pending = state.send()
  await state.send()
  assert.equal(calls, 1)
  fail(new Error('Błąd wysyłki')); await pending
  assert.equal(state.recipients.value[0].email, 'anna@example.com')
  assert.equal(state.error.value, 'Błąd wysyłki')
})

const invitation = { id: 'recipient-one', title: 'Umowa', filename: 'file.txt', version: 3, status: 'waiting', sender_name: 'Jan' }
test('inbox requires explicit confirmation and updates recipient status after acceptance', async () => {
  const calls = []
  const { state, events, mount } = component('./ApprovalInbox.vue', { api: async (path, method, body) => {
    calls.push({ path, method, body })
    return method ? { ...invitation, status: 'accepted', accepted_at: '2026-10-10T10:00:00Z' } : [invitation]
  } })
  await mount(); await new Promise(resolve => setImmediate(resolve))
  assert.equal(state.waiting.value, 1)
  state.open(invitation); await state.accept()
  assert.equal(calls.length, 1)
  state.confirmed.value = true; await state.accept()
  assert.equal(calls[1].path, '/approval-inbox/recipient-one/accept')
  assert.equal(calls[1].body.confirmed, true)
  assert.equal(state.waiting.value, 0)
  assert.equal(state.selected.value, null)
  assert.ok(events.some(event => event[0] === 'updated'))
  assert.ok(events.some(event => event[0] === 'loaded'))
})

test('expired invitations do not open acceptance; rejected acceptance keeps confirmation visible', async () => {
  const { state } = component('./ApprovalInbox.vue', { api: async () => { throw new Error('Dostęp cofnięty') } })
  state.open({ ...invitation, status: 'expired' })
  assert.equal(state.selected.value, null)
  state.open(invitation); state.confirmed.value = true
  await state.accept()
  assert.equal(state.selected.value.id, invitation.id)
  assert.equal(state.error.value, 'Dostęp cofnięty')
  assert.equal(state.busy.value, false)
})
