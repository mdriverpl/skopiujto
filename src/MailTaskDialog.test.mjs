import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
import { isEmailMessage, isSpamMessage } from './unifiedMail.js'

const compiled = compileScript(parse(readFileSync(new URL('./MailTaskDialog.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'mail-task-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
const email = { id: 'mail', folder: 'inbox', sender_email: 'sender@example.com', subject: 'Oferta', content: 'Sprawdz oferte' }
function dialog(api, message = email) {
  const events = [], mounted = [], context = { computed, ref, isEmailMessage, isSpamMessage,
    onMounted: callback => mounted.push(callback), CheckSquare: {}, Mail: {}, X: {} }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, message, currentUser: { id: 'me', name: 'Jan' }, smtpConfigured: true },
    { expose() {}, emit: (...args) => events.push(args) })
  const mount = async () => { for (const callback of mounted) await callback() }
  return { state, events, mount }
}
function mockApi(calls, send = () => ({ id: 'confirmation', folder: 'sent', version: 2 })) {
  return async (path, method, body) => {
    calls.push({ path, method, body })
    if (path === '/sharing-options') return { users: [{ id: 'employee', name: 'Anna' }] }
    if (path === '/tasks') return { id: 'task', ...body }
    if (path === '/client-mail/drafts') return { id: 'confirmation', folder: 'drafts', version: 1, ...body }
    if (path.startsWith('/client-mail?')) return [{ id: 'confirmation', folder: 'drafts', version: 1 }]
    if (path.endsWith('/send')) return send()
    throw new Error(`Unexpected API: ${path}`)
  }
}

test('creates an assigned task with message content and UTC deadline, then emails the original sender', async () => {
  const calls = [], { state, mount, events } = dialog(mockApi(calls))
  await mount()
  assert.equal(state.draft.value.description, email.content)
  assert.equal(state.users.value.length, 2)
  state.draft.value.assignee_id = 'employee'
  state.draft.value.due_at = '2026-10-20T15:30'
  await state.create()
  const task = calls.find(call => call.path === '/tasks')
  assert.equal(task.body.description, email.content)
  assert.equal(task.body.assignee_id, 'employee')
  assert.equal(task.body.source_mail_id, email.id)
  assert.equal(task.body.due_at, new Date('2026-10-20T15:30').toISOString())
  const confirmation = calls.find(call => call.path === '/client-mail/drafts')
  assert.ok(calls.indexOf(task) < calls.indexOf(confirmation))
  assert.equal(confirmation.body.recipient, email.sender_email)
  assert.equal(confirmation.body.subject, 'Re: Oferta')
  assert.ok(confirmation.body.content.includes(task.body.description))
  assert.ok(confirmation.body.content.includes('Termin realizacji:'))
  assert.equal(calls.at(-1).path, '/client-mail/confirmation/send')
  assert.equal(calls.at(-1).body.version, 1)
  assert.ok(events.some(([event]) => event === 'created'))
  assert.ok(events.some(([event]) => event === 'completed'))
  assert.equal(events.at(-1)[0], 'close')
})

test('SMTP failure keeps task and draft; retry sends confirmation without creating another task', async () => {
  const calls = []; let fail = true
  const { state, mount, events } = dialog(mockApi(calls, () => {
    if (fail) throw new Error('SMTP unavailable')
    return { id: 'confirmation', folder: 'sent', version: 2 }
  }))
  await mount()
  state.draft.value.due_at = '2026-10-20T15:30'
  await state.create()
  assert.equal(state.savedTask.value.id, 'task')
  assert.equal(state.confirmationDraft.value.id, 'confirmation')
  assert.match(state.error.value, /SMTP/)
  assert.equal(events.some(([event]) => event === 'close' || event === 'completed'), false)
  fail = false
  await state.create()
  assert.equal(calls.filter(call => call.path === '/tasks').length, 1)
  assert.equal(calls.filter(call => call.path === '/client-mail/drafts').length, 1)
  assert.equal(calls.filter(call => call.path.endsWith('/send')).length, 2)
  assert.equal(events.at(-1)[0], 'close')
})

test('retry checks delivery status and does not resend a confirmation already in sent mail', async () => {
  const calls = []
  const api = mockApi(calls, () => { throw new Error('Lost response') })
  let alreadySent = false
  const { state, mount } = dialog(async (path, ...args) => {
    if (alreadySent && path.startsWith('/client-mail?')) return [{ id: 'confirmation', folder: 'sent', version: 2 }]
    return api(path, ...args)
  })
  await mount()
  state.draft.value.due_at = '2026-10-20T15:30'
  await state.create()
  alreadySent = true
  await state.create()
  assert.equal(calls.filter(call => call.path.endsWith('/send')).length, 1)
})

test('portal messages create tasks without attempting email, and missing deadline prevents creation', async () => {
  const calls = [], { state, mount } = dialog(mockApi(calls), { ...email, sender_email: '', center: { source: 'internal', id: 'internal:one' } })
  await mount()
  await state.create()
  assert.equal(calls.some(call => call.path === '/tasks'), false)
  state.draft.value.due_at = '2026-10-20T15:30'
  await state.create()
  assert.equal(calls.filter(call => call.path === '/tasks').length, 1)
  assert.equal(calls.some(call => call.path.startsWith('/client-mail')), false)
  assert.equal(calls.find(call => call.path === '/tasks').body.source_mail_id, null)
  assert.equal(calls.find(call => call.path === '/tasks').body.source_message_id, 'internal:one')
})

test('task save failure prevents sending and keeps the editable form', async () => {
  const calls = [], api = mockApi(calls)
  const { state, mount } = dialog(async (path, ...args) => {
    if (path === '/tasks') throw new Error('Invalid assignee')
    return api(path, ...args)
  })
  await mount()
  state.draft.value.due_at = '2026-10-20T15:30'
  await state.create()
  assert.equal(state.savedTask.value, null)
  assert.match(state.error.value, /assignee/)
  assert.equal(calls.some(call => call.path.startsWith('/client-mail')), false)
})
