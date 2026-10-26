import { attachmentSelection, hasAttachmentChanges, saveAttachmentSelection, downloadMailArchive } from './composeAttachments.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
const compiled = compileScript(parse(readFileSync(new URL('./ChannelMessageDialog.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'channel-message-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
const contacts = [{ id: 'u:employee', name: 'Anna', source: 'Users', channels: { user: 'employee' } },
  { id: 'd:contact', name: 'Client', source: 'Clients', channels: { sms: '+48600123456', email: 'client@example.com' } }]
function dialog(api, channel = 'user', overrides = {}) {
  const mounted = [], events = [], context = { attachmentSelection, hasAttachmentChanges, saveAttachmentSelection, downloadMailArchive, FormData, ComposeAttachments: {}, URLSearchParams, computed, ref, onMounted: callback => mounted.push(callback), MessageChannelTabs: {} }
  runInNewContext(compiled, context)
  const state = context.component.setup({ api, channel, initialSubject: 'Meeting', initialContent: 'Tomorrow at 10', ...overrides },
    { expose() {}, emit: (...args) => events.push(args) })
  return { state, events, mount: async () => { for (const callback of mounted) await callback() } }
}
function api(calls) {
  return async (path, method, body) => {
    calls.push({ path, method, body })
    if (path.startsWith('/messages/contacts?')) return contacts
    if (path === '/ai/commands/options') return { dictionaries: [{ id: 'clients', name: 'Clients' }], channels: { user: { configured: true }, sms: { configured: true }, email: { configured: true } } }
    if (path === '/messages/prepare') return { id: 'job', ...body, recipients: [...body.recipients.map(id => ({ id, available: true })), ...(body.direct_email ? [{ id: 'm:direct', available: true }] : [])] }
    return { recipients: [{ id: 'recipient', status: 'sent' }] }
  }
}

test('portal selects only users and sends reviewed content through existing manual API', async () => {
  const calls = [], { state, mount, events } = dialog(api(calls))
  await mount()
  assert.equal(state.recipients.value.length, 1)
  assert.equal(state.recipients.value[0].id, 'u:employee')
  state.selected.value = ['u:employee']
  await state.send()
  const prepared = calls.find(call => call.path === '/messages/prepare')
  assert.equal(prepared.body.channel, 'user')
  assert.equal(prepared.body.source, 'users')
  const executed = calls.find(call => call.path.endsWith('/execute'))
  assert.equal(executed.body.confirmed, true)
  assert.equal(executed.body.message, 'Tomorrow at 10')
  assert.equal(events.at(-1)[0], 'sent')
})

test('group email snapshots computer and drive attachments before preparing delivery', async () => {
  const calls = [], base = api(calls)
  const transport = async (path, method, body) => {
    if (path === '/client-mail/drafts') return { id: 'attachments', version: 1, attachments: [], ...body }
    if (path.endsWith('/attachments')) {
      assert.equal(body.get('files').name, 'local.txt')
      assert.deepEqual(JSON.parse(body.get('drive_ids')), ['drive-file'])
      assert.equal(body.get('zip_password'), 'Saved-secret!')
      return { id: 'attachments', version: 2, attachments: [{ id: 'a', name: 'local.txt' }],
        zip_enabled: 1, zip_name: 'files.zip', zip_password: 'Saved-secret!' }
    }
    return base(path, method, body)
  }
  const { state, mount, events } = dialog(transport, 'email')
  await mount(); state.selected.value = ['d:contact']
  state.composeFiles.value = { ...attachmentSelection(), files: [new File(['local'], 'local.txt')],
    drive: [{ id: 'drive-file' }], zip_enabled: true, zip_name: 'files.zip', zip_password: 'Saved-secret!' }
  await state.send()
  assert.equal(calls.find(call => call.path === '/messages/prepare').body.attachment_mail_id, 'attachments')
  assert.equal(calls.find(call => call.path === '/messages/prepare').body.attachment_version, 2)
  assert.equal(events.at(-1)[0], 'sent')
})

test('SMS selects phone contacts and enforces SMS limit before preparing or sending', async () => {
  const calls = [], { state, mount } = dialog(api(calls), 'sms')
  await mount()
  assert.equal(state.recipients.value[0].id, 'd:contact')
  state.selected.value = ['d:contact']
  state.content.value = 'x'.repeat(1201)
  await state.send()
  assert.equal(calls.some(call => call.method), false)
  state.content.value = 'Reminder'
  await state.send()
  assert.equal(calls.find(call => call.path === '/messages/prepare').body.channel, 'sms')
  assert.equal(calls.find(call => call.path === '/messages/prepare').body.source, 'dictionaries')
})

test('switching channel keeps written subject and content', async () => {
  const { state, events } = dialog(async () => ({}), 'sms')
  state.content.value = 'Keep my draft'
  state.switchChannel('email')
  assert.equal(events[0][0], 'switch-channel')
  assert.equal(events[0][1].content, 'Keep my draft')
  assert.equal(events[0][1].subject, 'Meeting')
})

test('unavailable recipient prevents execution and preserves editable draft', async () => {
  const calls = [], normal = api(calls)
  const { state, mount } = dialog(async (path, ...args) => path === '/messages/prepare'
    ? { recipients: [{ name: 'Anna', available: false, reason: 'Inactive account' }] } : normal(path, ...args))
  await mount(); state.selected.value = ['u:employee']
  await state.send()
  assert.match(state.error.value, /Inactive account/)
  assert.equal(state.plan.value, null)
  assert.equal(state.content.value, 'Tomorrow at 10')
  assert.equal(calls.some(call => call.path.endsWith('/execute')), false)
})

test('failed delivery stays visible without claiming success or resending on another click', async () => {
  const calls = [], normal = api(calls)
  const { state, mount, events } = dialog(async (path, ...args) => path.endsWith('/execute')
    ? { recipients: [{ id: 'user', name: 'Anna', status: 'failed', reason: 'Delivery failed' }] } : normal(path, ...args))
  await mount(); state.selected.value = ['u:employee']
  await state.send()
  assert.equal(state.result.value.recipients[0].status, 'failed')
  assert.equal(state.canSend.value, false)
  assert.equal(events.some(([event]) => event === 'sent'), false)
})

test('select all affects only filtered recipients and switching dictionaries clears old selections', async () => {
  const calls = [], normal = api(calls)
  const { state, mount } = dialog(async (path, ...args) => path.startsWith('/messages/contacts?')
    ? [{ id: 'd:one', name: 'Anna', source: 'Clients', channels: { email: 'anna@example.com' } },
       { id: 'd:two', name: 'Jan', source: 'Clients', channels: { email: 'jan@example.com' } }]
    : normal(path, ...args), 'email')
  await mount()
  state.toggleAll(); assert.equal(state.selected.value.length, 2); assert.equal(state.allSelected.value, true)
  state.search.value = 'Anna'; state.toggleAll()
  assert.equal(state.selected.value.length, 1); assert.equal(state.selected.value[0], 'd:two')
  state.search.value = ''; assert.equal(state.someSelected.value, true)
  state.dictionaryId.value = 'clients'
  await state.loadContacts()
  assert.equal(state.selected.value.length, 0)
  assert.equal(state.plan.value, null)
  state.toggleAll(); await state.send()
  assert.equal(calls.find(call => call.path === '/messages/prepare').body.dictionary_id, 'clients')
})

test('sending all contacts splits large selections into supported batches without omitting recipients', async () => {
  const prepared = [], executed = []
  const { state, mount, events } = dialog(async (path, method, body) => {
    if (path === '/ai/commands/options') return { channels: { user: { configured: true } } }
    if (path.startsWith('/messages/contacts?')) return Array.from({ length: 205 }, (_, i) => ({
      id: `u:${i}`, name: `User ${i}`, source: 'Users', channels: { user: String(i) } }))
    if (path === '/messages/prepare') {
      prepared.push(body)
      return { id: String(prepared.length), ...body, recipients: body.recipients.map(id => ({ id, available: true })) }
    }
    executed.push(...body.recipients)
    return { recipients: body.recipients.map(id => ({ id, status: 'sent' })) }
  })
  await mount(); state.toggleAll(); await state.send()
  assert.deepEqual(prepared.map(batch => batch.recipients.length), [100, 100, 5])
  assert.equal(new Set(executed).size, 205)
  assert.equal(state.result.value.recipients.length, 205)
  assert.equal(events.at(-1)[0], 'sent')
})

test('choosing history preserves written text and accepts a direct email', async () => {
  const calls = [], { state, mount, events } = dialog(api(calls), 'email')
  await mount()
  await state.chooseSource('history')
  assert.ok(calls.some(call => call.path.includes('source=history')))
  assert.equal(state.subject.value, 'Meeting')
  assert.equal(state.content.value, 'Tomorrow at 10')
  state.directEmail.value = 'new-client@example.com'
  await state.send()
  const prepared = calls.find(call => call.path === '/messages/prepare')
  assert.equal(prepared.body.direct_email, 'new-client@example.com')
  assert.equal(prepared.body.source, 'history')
  assert.equal(prepared.body.dictionary_id, null)
  assert.equal(events.at(-1)[0], 'sent')
})

test('single portal reply preselects original sender and prevents channel changes', async () => {
  const calls = [], { state, mount, events } = dialog(api(calls), 'user', { group: false, reply: true, initialRecipientId: 'u:employee' })
  await mount()
  assert.equal(state.directEmail.value, 'Anna')
  assert.equal(state.selected.value[0], 'u:employee')
  assert.equal(state.recipientCount.value, 1)
  state.switchChannel('email')
  assert.equal(events.length, 0)
  await state.send()
  assert.equal(calls.find(call => call.path === '/messages/prepare').body.recipients[0], 'u:employee')
})

test('single SMS accepts a typed phone number and changing a contact clears the old recipient', async () => {
  const calls = [], { state, mount } = dialog(api(calls), 'sms', { group: false })
  await mount()
  state.directEmail.value = '+48600123456'; state.pickRecipient()
  assert.equal(state.selected.value[0], 'd:contact')
  state.directEmail.value = '+48600999888'; state.pickRecipient()
  assert.equal(state.selected.value.length, 0)
  await state.send()
  assert.equal(calls.find(call => call.path === '/messages/prepare').body.direct_sms, '+48600999888')
})
