import { attachmentSelection, hasAttachmentChanges, saveAttachmentSelection, downloadMailArchive } from './composeAttachments.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch, reactive, nextTick } from 'vue'
import { mailSenderKind } from './mailSenderKind.js'
import { loadUnifiedMail, isEmailMessage, isSpamMessage, isReceivedMessage, sourceKind } from './unifiedMail.js'

const compiled = compileScript(parse(readFileSync(new URL('./ClientMail.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'mail-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api, overrides = {}, emit = () => {}, fetcher = globalThis.fetch, localStorage, mobile = false) {
  const mounted = []
  const context = { attachmentSelection, hasAttachmentChanges, saveAttachmentSelection, downloadMailArchive, FormData, ComposeAttachments: {}, mailSenderKind, loadUnifiedMail, isEmailMessage, isSpamMessage, isReceivedMessage, sourceKind, computed, ref, watch, localStorage, onMounted(callback) { mounted.push(callback) }, FormData, fetch: fetcher, MailSettings: {}, MailTaskDialog: {}, MessageChannelTabs: {}, ChannelMessageDialog: {} }
  for (const icon of ['ClipboardPlus', 'Mail', 'Users', 'MessageSquare', 'Inbox', 'Send', 'FileText', 'Archive', 'ShieldAlert', 'Trash2', 'Handshake', 'Landmark', 'UserRound', 'Megaphone', 'Bell', 'Ban']) context[icon] = {}
  context.matchMedia = () => ({ matches: mobile })
  runInNewContext(compiled, context)
  const state = context.component.setup(reactive({ api, ...overrides }), { expose() {}, emit })
  state.mount = async () => { for (const callback of mounted) await callback() }
  return state
}
const message = { id: 'one', folder: 'inbox', sender_name: 'Jan Kowalski', sender_email: 'jan@example.com',
  recipient: 'ja@example.com', subject: 'Oferta', content: 'Warunki współpracy', unread: 1, label: 'urgent',
  version: 1, created_at: '2026-10-13T10:00:00Z', attachments: [{ id: 'a', name: 'Oferta.pdf' }] }

test('sending a reply preserves the current folder and message', async () => {
  const events = []
  const state = panel(async (path, method, body) => ({ ...message, ...body,
    id: 'draft', folder: path.endsWith('/send') ? 'sent' : 'drafts', attachments: [] }), {}, (...args) => events.push(args))
  state.messages.value = [{ ...message }]
  state.selectedId.value = message.id
  state.compose(message, 'reply')
  await state.send()
  assert.equal(state.folder.value, 'inbox')
  assert.equal(state.selectedId.value, message.id)
  assert.equal(state.composer.value, null)
  assert.equal(state.messages.value.find(item => item.id === 'draft').folder, 'sent')
  assert.equal(events.some(([name]) => name === 'folder-change'), false)
})

for (const mobile of [false, true]) test(`deleting returns to ${mobile ? 'the mobile list' : 'the first visible desktop message'}`, async () => {
  const state = panel(async (path, method, body) => ({ ...message, ...body, version: 2 }), {}, () => {}, globalThis.fetch, undefined, mobile)
  const first = { ...message, id: 'first', unread: false, created_at: '2026-10-14T10:00:00Z' }
  state.messages.value = [first, { ...message }]
  state.selectedId.value = message.id
  await state.deleteMessage(state.selected.value)
  assert.equal(state.selectedId.value, mobile ? null : 'first')
  assert.equal(state.filtered.value.length, 1)
  assert.equal(state.folder.value, 'inbox')
})

test('deleting the last message clears selection; failed deletion preserves the message', async () => {
  const state = panel(async (path, method, body) => ({ ...message, ...body }))
  state.messages.value = [{ ...message }]; state.selectedId.value = message.id
  await state.deleteMessage(state.selected.value)
  assert.equal(state.selectedId.value, null)
  assert.equal(state.filtered.value.length, 0)
  const failed = panel(async () => { throw new Error('Delete failed') })
  failed.messages.value = [{ ...message }]; failed.selectedId.value = message.id
  await failed.deleteMessage(failed.selected.value)
  assert.equal(failed.selectedId.value, message.id)
  assert.equal(failed.filtered.value.length, 1)
  assert.equal(failed.error.value, 'Delete failed')
})

test('left swipe reveals delete, right swipe closes it, and vertical scrolling does neither', () => {
  const state = panel(async () => { throw new Error('Swipe must not call API') })
  let prevented = false
  const start = () => state.startMessageSwipe({ touches: [{ clientX: 180, clientY: 80 }] }, message)
  const end = (x, y) => state.endMessageSwipe({ changedTouches: [{ clientX: x, clientY: y }], cancelable: true,
    preventDefault() { prevented = true } }, message)
  start(); end(70, 85)
  assert.equal(state.swipeMessageId.value, message.id)
  assert.equal(prevented, true)
  start(); end(270, 85)
  assert.equal(state.swipeMessageId.value, null)
  prevented = false
  start(); end(110, 300)
  assert.equal(state.swipeMessageId.value, null)
  assert.equal(prevented, false)
  state.startMessageSwipe({ touches: [{ clientX: 180, clientY: 80 }] }, { ...message, folder: 'trash' })
  end(70, 85)
  assert.equal(state.swipeMessageId.value, null)
})

test('failed SMTP keeps uploaded attachments and ZIP settings in the saved draft for retry', async () => {
  const calls = []
  const api = async (path, method, body) => {
    calls.push({ path, method, body })
    if (path === '/client-mail/drafts') return { ...message, id: 'draft-files', folder: 'drafts', attachments: [], version: 1, ...body }
    if (path.endsWith('/attachments')) return { ...message, id: 'draft-files', folder: 'drafts', version: 2,
      attachments: [{ id: 'uploaded', name: 'Contract.pdf', size: 8 }], zip_enabled: 1, zip_name: 'files.zip', zip_password: 'Secret!' }
    if (path.endsWith('/send')) throw new Error('SMTP unavailable')
  }
  const state = panel(api)
  state.compose()
  state.composer.value = { recipient: 'anna@example.com', subject: 'Files', content: 'Attached' }
  state.composeFiles.value = { ...attachmentSelection(), files: [new File(['contract'], 'Contract.pdf')],
    zip_enabled: true, zip_name: 'files.zip', zip_password: 'Secret!' }
  await state.send()
  const request = calls.find(call => call.path.endsWith('/attachments'))
  assert.equal(request.body.get('files').name, 'Contract.pdf')
  assert.equal(request.body.get('zip_password'), 'Secret!')
  assert.equal(state.composer.value.id, 'draft-files')
  assert.equal(state.composer.value.version, 2)
  assert.equal(state.composeFiles.value.existing[0].id, 'uploaded')
  assert.equal(state.composeFiles.value.files.length, 0)
  assert.equal(state.composeFiles.value.zip_password, 'Secret!')
  assert.match(state.error.value, /SMTP unavailable/)
})

test('single compose, group compose and replies keep their own layout and source', () => {
  const state = panel(async () => ({}))
  state.compose(); assert.equal(state.composerDictionaryMode.value, false)
  state.compose(null, 'group'); assert.equal(state.composerDictionaryMode.value, true)
  state.switchComposeChannel({ channel: 'sms', subject: 'Test', content: 'Body', recipient: '' })
  assert.equal(state.composerDictionaryMode.value, true)
  state.compose(message, 'reply')
  assert.equal(state.composerReply.value, true)
  assert.equal(state.composerChannel.value, 'email')
  assert.equal(state.composer.value.recipient, 'jan@example.com')
  state.compose({ ...message, sender_email: '', center: { channel: 'user', reply_to: { id: 'u:anna', name: 'Anna' } } }, 'reply')
  assert.equal(state.composerChannel.value, 'user')
  assert.equal(state.composer.value.recipientId, 'u:anna')
  assert.equal(state.composerDictionaryMode.value, false)
})

test('restored mailbox loads all sources and opens portal messages without email requests', async () => {
  const calls = []
  const state = panel(async (path, method) => {
    calls.push([path, method])
    if (path === '/client-mail?folder=inbox') return [message]
    if (path.startsWith('/message-center?')) return { total: 1, items: [
      { id: 'internal:portal', source: 'internal', source_id: 'portal', channel: 'user', title: 'Przez portal',
        sender: 'Anna', recipient: 'Jan', unread: true, created_at: '2000-01-01T12:00:00Z' }
    ] }
    if (path === '/message-center/internal%3Aportal/read-state') return { unread: false }
    return { account: { imap: { enabled: false } } }
  }, { unified: true })
  await state.load()
  assert.equal(state.filtered.value.length, 2)
  assert.equal(state.unifiedHours.value, null)
  const portal = state.messages.value.find(item => item.center.source === 'internal')
  assert.equal(portal.sender_email, '')
  await state.open(portal)
  assert.equal(state.selected.value.id, 'internal:portal')
  assert.equal(state.selected.value.unread, false)
  assert.equal(state.composer.value, null)
  assert.ok(calls.some(([path, method]) => path === '/message-center/internal%3Aportal/read-state' && method === 'PATCH'))
  assert.equal(calls.some(([path, method]) => path.startsWith('/client-mail/') && method === 'PATCH'), false)
  const previousCalls = calls.length
  await state.patch(portal, { unread: false })
  assert.equal(calls.length, previousCalls)
})

test('unread stars persist email and other channel status without opening the message', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    return path.startsWith('/message-center/') ? { unread: body.unread } : { ...message, ...body, version: 2 }
  }, { unified: true })
  const delivery = { ...message, id: 'edelivery:one', unread: true,
    center: { id: 'edelivery:one', source: 'edelivery', direction: 'incoming', unread: true } }
  state.messages.value = [{ ...message, unread: false }, delivery]
  state.filter.value = 'unread'
  assert.equal(state.filtered.value.length, 1)
  await state.setUnread(state.messages.value[0], true)
  assert.equal(calls[0].body.unread, true)
  assert.equal('starred' in calls[0].body, false)
  assert.equal(state.selectedId.value, null)
  assert.equal(state.filtered.value.length, 2)
  await state.open(delivery)
  assert.equal(delivery.unread, false)
  assert.equal(state.unread.value, 1)
  await state.setUnread(delivery, true)
  assert.equal(delivery.unread, true)
  assert.equal(delivery.center.unread, true)
  assert.equal(calls.at(-1).path, '/message-center/edelivery%3Aone/read-state')
  assert.equal(state.filtered.value.length, 2)
})

test('failed read status save leaves the unread star and count unchanged', async () => {
  const state = panel(async () => { throw new Error('Save failed') }, { unified: true })
  const delivery = { ...message, id: 'edelivery:one', center: { id: 'edelivery:one', source: 'edelivery' } }
  state.messages.value = [delivery]
  await state.open(delivery)
  assert.equal(delivery.unread, 1)
  assert.equal(state.unread.value, 1)
  assert.match(state.error.value, /Save failed/)
})

test('filters search attachments, labels and folders; opening persists read status', async () => {
  const calls = []
  const state = panel(async (path, method, body) => { calls.push({ path, method, body }); return { ...message, ...body, version: 2 } })
  state.messages.value = [message, { ...message, id: 'two', folder: 'spam' }]
  state.search.value.filename = 'OFERTA.PDF'
  assert.equal(state.filtered.value.length, 1)
  state.filter.value = 'payment'
  assert.equal(state.filtered.value.length, 0)
  state.filter.value = 'urgent'
  await state.open(message)
  assert.equal(calls[0].body.unread, false)
  assert.equal(state.selected.value.version, 2)
  assert.equal(state.unread.value, 0)
})

test('moving unified mail to spam immediately removes it from received rows and unread count', async () => {
  const state = panel(async (path, method, body) => ({ ...message, ...body, version: 2 }), { unified: true })
  state.messages.value = [{ ...message, center: { source: 'email', folder: 'inbox' } },
    { ...message, id: 'classified', category: 'spam' }]
  assert.equal(state.filtered.value.length, 1)
  assert.equal(state.unread.value, 1)
  await state.patch(state.messages.value[0], { folder: 'spam' })
  assert.equal(state.filtered.value.length, 0)
  assert.equal(state.unread.value, 0)
  const spam = panel(async () => {}, { initialFolder: 'spam' })
  spam.messages.value = state.messages.value
  assert.equal(spam.filtered.value.length, 2)
  assert.equal(spam.filtered.value[0].id, message.id)
})

test('received rows exclude outgoing messages and immediately hide archived or sent emails', async () => {
  const state = panel(async (path, method, body) => ({ ...message, ...body, version: 2 }), { unified: true })
  state.messages.value = [message, { ...message, id: 'sent', folder: 'sent' },
    { ...message, id: 'portal-out', center: { source: 'internal', direction: 'outgoing' } }]
  assert.equal(state.filtered.value.length, 1)
  assert.equal(state.unread.value, 1)
  await state.patch(message, { folder: 'archive' })
  assert.equal(state.filtered.value.length, 0)
  assert.equal(state.unread.value, 0)
  const sent = panel(async () => {}, { initialFolder: 'sent' })
  sent.messages.value = state.messages.value
  assert.equal(sent.filtered.value.length, 1)
  assert.equal(sent.filtered.value[0].id, 'sent')
})

test('time range survives returning to inbox and reloads, with independent folder settings', async () => {
  const saved = new Map()
  const storage = { getItem: key => saved.get(key) ?? null, setItem: (key, value) => saved.set(key, value) }
  const api = async path => path === '/client-mail/settings' ? { account: { imap: { enabled: false } } }
    : path.startsWith('/message-center?') ? { items: [], total: 0 } : []
  const create = props => panel(api, props, () => {}, globalThis.fetch, storage)
  const inbox = create({ unified: true, initialFolder: 'inbox' })
  await inbox.changeTimeRange(24)
  const restored = create({ unified: true, initialFolder: 'inbox' })
  assert.equal(restored.unifiedHours.value, 24)
  assert.equal(restored.syncHours.value, 24)
  const sent = create({ initialFolder: 'sent' })
  await sent.changeTimeRange(168)
  assert.equal(create({ unified: true, initialFolder: 'inbox' }).unifiedHours.value, 24)
  assert.equal(create({ initialFolder: 'sent' }).syncHours.value, 168)
  restored.showAllTime()
  assert.equal(create({ unified: true, initialFolder: 'inbox' }).unifiedHours.value, null)
  sent.changeFolder('inbox')
  assert.equal(sent.syncHours.value, 24)
  sent.changeFolder('sent')
  assert.equal(sent.syncHours.value, 168)
  saved.set('edokumenty-mail-range:inbox', 'invalid')
  assert.equal(create({ unified: true, initialFolder: 'inbox' }).unifiedHours.value, null)
})

test('new message count follows the active time range and excludes spam and outgoing mail', () => {
  const state = panel(async () => {}, { unified: true })
  const recent = new Date(Date.now() - 2 * 3600000).toISOString()
  const older = new Date(Date.now() - 30 * 3600000).toISOString()
  state.messages.value = [
    { ...message, id: 'new', created_at: recent },
    { ...message, id: 'older', created_at: older },
    { ...message, id: 'read', created_at: recent, unread: false },
    { ...message, id: 'spam', created_at: recent, folder: 'spam' },
    { ...message, id: 'classified-spam', created_at: recent, category: 'spam' },
    { ...message, id: 'sent', created_at: recent, folder: 'sent' }
  ]
  state.unifiedHours.value = 24
  assert.equal(state.unread.value, 1)
  state.unifiedHours.value = 48
  assert.equal(state.unread.value, 2)
  state.headerSearch.value = 'no match'
  assert.equal(state.unread.value, 0)
  state.headerSearch.value = ''
  state.showAllTime()
  assert.equal(state.unread.value, 2)
})

test('SMTP failure keeps saved draft and editable text for retry', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (path.endsWith('/send')) throw new Error('SMTP unavailable')
    return { ...message, ...body, id: 'draft', folder: 'drafts', attachments: [] }
  })
  state.compose(message, 'reply')
  assert.equal(state.composer.value.recipient, message.sender_email)
  state.composer.value.content = 'Moja odpowiedź'
  await state.send()
  assert.equal(calls[0].path, '/client-mail/drafts')
  assert.equal(calls[1].path, '/client-mail/draft/send')
  assert.equal(state.composer.value.content, 'Moja odpowiedź')
  assert.equal(state.composer.value.id, 'draft')
  assert.match(state.error.value, /SMTP/)
  assert.equal(state.messages.value[0].folder, 'drafts')
})

test('AI result stays with analyzed message and using response makes an unsent draft', async () => {
  let resolve
  const state = panel(() => new Promise(r => { resolve = r }))
  state.messages.value = [message, { ...message, id: 'two' }]
  state.selectedId.value = 'one'
  const pending = state.analyze()
  state.selectedId.value = 'two'
  resolve({ summary: 'Oferta', tasks: [], priority: 'high', reply: 'Dziękuję za ofertę.' })
  await pending
  assert.equal(state.currentAnalysis.value, undefined)
  state.selectedId.value = 'one'
  state.useReply()
  assert.equal(state.composer.value.content, 'Dziękuję za ofertę.')
  assert.equal(state.composer.value.id, undefined)
  assert.equal(state.composer.value.recipient, 'jan@example.com')
})

test('refresh receives IMAP mail before reloading the local list', async () => {
  const calls = []
  const state = panel(async (path, method) => {
    calls.push([path, method])
    if (path === '/client-mail/settings') return { account: { imap: { enabled: true } } }
    if (path === '/client-mail/sync') return { imported: 1, skipped: 0, remaining: 0 }
    return [message]
  })
  await state.refresh()
  assert.equal(calls.filter(([path]) => path === '/client-mail/sync').length, 1)
  assert.equal(calls.find(([path]) => path === '/client-mail/sync')[1], 'POST')
  assert.equal(state.messages.value[0].id, 'one')
  assert.match(state.notice.value, /1/)
})

test('time range controls synchronization and limits the mailbox response', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (path === '/client-mail/settings') return { account: { imap: { enabled: true } } }
    if (path === '/client-mail/sync') return { imported: 0, skipped: 0, remaining: 0 }
    return [message]
  })
  assert.equal(state.syncHours.value, 24)
  state.selectedId.value = 'one'
  await state.changeTimeRange(168)
  assert.equal(state.syncHours.value, 168)
  assert.equal(state.selectedId.value, null)
  assert.equal(calls.find(call => call.path === '/client-mail/sync').body.hours, 168)
  assert.equal(calls.some(call => call.path === '/client-mail?hours=168'), true)
  const count = calls.length
  await state.changeTimeRange(168)
  assert.equal(calls.length, count)
})

test('mail search combines independent fields and resets them together', () => {
  const state = panel(async () => {})
  state.messages.value = [message, { ...message, id: 'other', subject: 'Inny temat', attachments: [] }]
  state.search.value = { email: ' JAN@EXAMPLE.COM ', subject: 'oferta', content: 'WSPÓŁPRACY', filename: '.pdf' }
  assert.deepEqual(Array.from(state.filtered.value, item => item.id), ['one'])
  state.search.value.content = 'Oferta.pdf'
  assert.equal(state.filtered.value.length, 0)
  state.clearSearch()
  assert.equal(state.filtered.value.length, 2)
  state.search.value.email = 'ja@example.com'
  assert.equal(state.filtered.value.length, 2)
  state.search.value.filename = 'missing.txt'
  assert.equal(state.filtered.value.length, 0)
})

test('header search finds mail fields and combines with detailed search', () => {
  const state = panel(async () => {})
  state.messages.value = [message, { ...message, id: 'other', sender_email: 'other@example.com', subject: 'Inny temat', attachments: [] }]
  state.headerSearch.value = ' OFERTA.PDF '
  assert.deepEqual(Array.from(state.filtered.value, item => item.id), ['one'])
  state.headerSearch.value = 'JAN@EXAMPLE.COM'
  assert.equal(state.filtered.value.length, 1)
  state.search.value.subject = 'Inny temat'
  assert.equal(state.filtered.value.length, 0)
  state.headerSearch.value = ''
  assert.deepEqual(Array.from(state.filtered.value, item => item.id), ['other'])
})

test('company assignment sends selected scope and reloads related messages', async () => {
  const calls = []
  const linked = { ...message, safe: true, company: { id: 'company', name: 'Firma Alfa' }, version: 2 }
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (path === '/client-mail/companies') return [{ id: 'company', name: 'Firma Alfa' }]
    if (path.endsWith('/company')) return linked
    if (path.endsWith('/settings')) return { account: { imap: { enabled: false } } }
    return [linked]
  })
  state.messages.value = [message]; state.selectedId.value = message.id
  await state.editCompany()
  state.companyEditor.value.scope = 'domain'
  state.companyEditor.value.entry_id = 'company'
  await state.saveCompany()
  const request = calls.find(call => call.path.endsWith('/company'))
  assert.equal(request.body.scope, 'domain')
  assert.equal(request.body.entry_id, 'company')
  assert.equal(request.body.version, 1)
  assert.equal(state.selected.value.safe, true)
  assert.equal(state.companyEditor.value, null)
})

test('blocking stays in the current folder and confirms movement; unblocking remains available in spam', async () => {
  const calls = []
  const events = []
  let blocked = false
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (path.endsWith('/spam-address')) { blocked = method === 'POST'; return {} }
    if (path.endsWith('/settings')) return { account: { imap: { enabled: false } } }
    return [{ ...message, blocked, folder: 'spam', version: blocked ? 2 : 3 }]
  }, {}, (...args) => events.push(args))
  state.messages.value = [message]; state.selectedId.value = message.id
  await state.spamSender()
  assert.equal(state.folder.value, 'inbox')
  assert.equal(state.selected.value, undefined)
  assert.equal(state.filtered.value.length, 0)
  assert.equal(state.spamFeedback.value, true)
  assert.equal(events.length, 0)
  state.changeFolder('spam'); state.selectedId.value = message.id
  assert.equal(state.selected.value.blocked, true)
  await state.spamSender()
  const requests = calls.filter(call => call.path.endsWith('/spam-address'))
  assert.deepEqual(requests.map(call => call.method), ['POST', 'DELETE'])
  assert.equal(requests[1].body.version, 2)
  assert.equal(state.selected.value.blocked, false)
  assert.equal(state.spamFeedback.value, false)
})

test('moving a message to spam keeps the current folder and clears its preview only after success', async () => {
  const state = panel(async (path, method, body) => ({ ...message, ...body, version: 2 }))
  state.messages.value = [message]; state.selectedId.value = message.id
  await state.run(() => state.patch(message, { folder: 'spam' }))
  assert.equal(state.folder.value, 'inbox')
  assert.equal(state.selected.value, undefined)
  assert.equal(state.filtered.value.length, 0)
  assert.equal(state.spamFeedback.value, true)
})

test('failed spam blocking keeps the message visible without a success animation', async () => {
  const state = panel(async () => { throw new Error('Brak połączenia') })
  state.messages.value = [message]; state.selectedId.value = message.id
  await state.spamSender()
  assert.equal(state.folder.value, 'inbox')
  assert.equal(state.selected.value.id, message.id)
  assert.equal(state.spamFeedback.value, false)
  assert.match(state.error.value, /Brak/)
})

test('trusted sender cannot trigger spam blocking', async () => {
  const calls = []
  const state = panel(async (...args) => { calls.push(args) })
  for (const trust of [{ safe: true }, { company: { id: 'company', name: 'Firma' } }, { spam_protected: true }]) {
    state.messages.value = [{ ...message, ...trust }]
    state.selectedId.value = message.id
    await state.spamSender()
    assert.equal(calls.length, 0)
    assert.equal(state.selected.value.folder, 'inbox')
  }
})

test('opening mail scans locally without changing the current folder', async () => {
  const calls = []
  const state = panel(async (path, method) => {
    calls.push({ path, method })
    if (path.startsWith('/client-mail/spam-scan?')) return { moved: 1 }
    if (path.endsWith('/settings')) return { account: { imap: { enabled: false } } }
    return [{ ...message, folder: 'spam' }]
  })
  await state.mount()
  assert.equal(calls[0].path, '/client-mail/spam-scan?hours=24')
  assert.equal(calls[0].method, 'POST')
  assert.equal(state.folder.value, 'inbox')
  assert.equal(state.filtered.value.length, 0)
  assert.equal(state.spamFeedback.value, true)
})

test('message labels save and reload independently for each message', async () => {
  let stored = [{ ...message }, { ...message, id: 'second', label: 'offer' }]
  const api = async (path, method, body) => {
    if (path.startsWith('/client-mail/spam-scan?')) return { moved: 0 }
    if (path.endsWith('/settings')) return { account: { imap: { enabled: false } } }
    if (method === 'PATCH') {
      const id = path.split('/').at(-1)
      stored = stored.map(item => item.id === id ? { ...item, ...body, version: item.version + 1 } : item)
      return stored.find(item => item.id === id)
    }
    return stored
  }
  const state = panel(api)
  await state.mount()
  for (const label of ['invoice', 'offer', 'urgent', '']) {
    await state.patch(state.messages.value.find(item => item.id === message.id), { label })
    const reopened = panel(api)
    await reopened.mount()
    reopened.selectedId.value = message.id
    assert.equal(reopened.selected.value.label, label)
    reopened.selectedId.value = 'second'
    assert.equal(reopened.selected.value.label, 'offer')
  }
})

test('list label menu updates its own message without opening or marking it as read', async () => {
  const calls = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    return { ...message, id: 'second', ...body, version: 2 }
  })
  state.messages.value = [{ ...message }, { ...message, id: 'second', label: '' }]
  state.selectedId.value = message.id
  state.labelTargetId.value = 'second'
  await state.chooseLabel('invoice')
  assert.equal(calls[0].path, '/client-mail/second')
  assert.equal(calls[0].body.label, 'invoice')
  assert.equal(calls[0].body.version, 1)
  assert.equal('unread' in calls[0].body, false)
  assert.equal(state.selectedId.value, message.id)
  assert.equal(state.messages.value.find(item => item.id === message.id).label, 'urgent')
  assert.equal(state.labelTarget.value.label, 'invoice')
})

test('a scan failure still loads the mailbox and shows the error', async () => {
  const state = panel(async path => {
    if (path.startsWith('/client-mail/spam-scan?')) throw new Error('Filtr niedostępny')
    if (path.endsWith('/settings')) return { account: { imap: { enabled: false } } }
    return [message]
  })
  await state.mount()
  assert.equal(state.filtered.value.length, 1)
  assert.match(state.error.value, /Filtr/)
})

test('failed company save preserves the editor for correction', async () => {
  const state = panel(async () => { throw new Error('Konflikt wersji') })
  state.companyEditor.value = { messageId: 'one', version: 1, scope: 'email', name: 'Firma Alfa', entry_id: '' }
  await state.saveCompany()
  assert.equal(state.companyEditor.value.name, 'Firma Alfa')
  assert.match(state.error.value, /Konflikt/)
})

test('removing a company unlinks only the selected email and reloads without a spam scan', async () => {
  const calls = []
  const linked = { ...message, company: { id: 'company', name: 'Firma Alfa' }, safe: true }
  const unlinked = { ...message, company: null, safe: false, version: 2 }
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (method === 'DELETE') return unlinked
    if (path.endsWith('/settings')) return {}
    return [unlinked]
  })
  state.messages.value = [linked]; state.selectedId.value = linked.id
  await state.removeCompany()
  assert.equal(calls[0].path, '/client-mail/one/company')
  assert.equal(calls[0].method, 'DELETE')
  assert.equal(calls[0].body.entry_id, 'company')
  assert.equal(calls[0].body.version, 1)
  assert.equal(state.selected.value.company, null)
  assert.equal(state.selected.value.folder, 'inbox')
  assert.equal(calls.some(call => call.path.startsWith('/client-mail/spam-scan?')), false)
})

test('category filter combines with search and folder changes clear it', () => {
  const state = panel(async () => {})
  state.messages.value = [
    { ...message, category: 'invoice' },
    { ...message, id: 'ad', category: 'advertisement' },
    { ...message, id: 'uncategorized' }
  ]
  state.categoryFilter.value = 'invoice'
  assert.deepEqual(Array.from(state.filtered.value, item => item.id), ['one'])
  state.search.value.subject = 'missing'
  assert.equal(state.filtered.value.length, 0)
  state.clearSearch()
  state.categoryFilter.value = 'uncategorized'
  assert.deepEqual(Array.from(state.filtered.value, item => item.id), ['uncategorized'])
  state.changeFolder('archive')
  assert.equal(state.categoryFilter.value, '')
})

test('saving attachments creates a nested portal folder and uploads exact bytes through existing file API', async () => {
  const calls = [], downloads = []
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (path === '/folders' && !method) return [{ id: 'parent', name: 'Klienci', parent_id: null, permissions: { read: true, add: true } }]
    if (path === '/access') return { read: true, add: true }
    if (path === '/folders' && method === 'POST') return { id: 'new-folder', name: body.name, parent_id: body.parent_id }
    if (path === '/files') return { id: 'saved' }
    throw new Error('Unexpected path')
  }, {}, () => {}, async (path, options) => {
    downloads.push({ path, options })
    return { ok: true, blob: async () => new Blob(['exact attachment bytes']) }
  })
  state.messages.value = [message]; state.selectedId.value = message.id
  await state.openDriveDialog(message.attachments[0])
  state.driveDialog.value.destination = 'parent'
  state.driveDialog.value.createFolder = true
  state.driveDialog.value.newName = '  Faktury  '
  await state.saveToDrive()
  const folder = calls.find(call => call.method === 'POST' && call.path === '/folders')
  assert.equal(folder.body.name, 'Faktury')
  assert.equal(folder.body.parent_id, 'parent')
  assert.equal(folder.body.access_mode, 'inherit')
  const upload = calls.find(call => call.path === '/files')
  assert.equal(upload.body.get('folder_id'), 'new-folder')
  assert.equal(upload.body.get('file').name, 'Oferta.pdf')
  assert.equal(await upload.body.get('file').text(), 'exact attachment bytes')
  assert.equal(downloads[0].path, '/api/client-mail/one/attachments/a')
  assert.equal(downloads[0].options.credentials, 'same-origin')
  assert.equal(state.driveDialog.value, null)
  assert.match(state.notice.value, /Klienci.*Faktury/)
})

test('drive picker defaults to writable shared folder and prevents saving without add rights', async () => {
  const state = panel(async path => path === '/folders' ? [
    { id: 'read-only', name: 'Podgląd', parent_id: null, permissions: { read: true, add: false } },
    { id: 'shared', name: 'Wspólny', parent_id: 'read-only', permissions: { read: true, add: true } }
  ] : { read: true, add: false })
  state.messages.value = [message]; state.selectedId.value = message.id
  await state.openDriveDialog()
  assert.equal(state.driveDialog.value.destination, 'shared')
  assert.equal(state.canSaveToDrive.value, true)
  assert.match(state.drivePath('shared'), /Podgląd.*Wspólny/)
  state.driveDialog.value.destination = 'read-only'
  assert.equal(state.canSaveToDrive.value, false)
  state.driveDialog.value.destination = null
  assert.equal(state.canSaveToDrive.value, false)
})

test('failed batch preserves the created folder and retries only unsaved attachments', async () => {
  let uploads = 0, creates = 0, fail = true
  const savedNames = []
  const state = panel(async (path, method, body) => {
    if (path === '/folders' && !method) return []
    if (path === '/access') return { read: true, add: true }
    if (path === '/folders') { creates++; return { id: 'created', name: body.name, parent_id: null } }
    if (path === '/files') {
      uploads++
      if (uploads === 2 && fail) throw new Error('Magazyn niedostępny')
      savedNames.push(body.get('file').name)
      return { id: String(uploads) }
    }
  }, {}, () => {}, async () => ({ ok: true, blob: async () => new Blob(['data']) }))
  state.messages.value = [{ ...message, attachments: [...message.attachments, { id: 'b', name: 'Drugi.pdf' }] }]
  state.selectedId.value = message.id
  await state.openDriveDialog()
  state.driveDialog.value.createFolder = true; state.driveDialog.value.newName = 'Nowy'
  await state.saveToDrive()
  assert.equal(state.driveDialog.value.destination, 'created')
  assert.equal(state.driveDialog.value.createFolder, false)
  assert.deepEqual(Array.from(state.driveDialog.value.chosen), ['b'])
  assert.match(state.driveError.value, /Zapisano już: 1/)
  fail = false
  await state.saveToDrive()
  assert.equal(creates, 1)
  assert.deepEqual(savedNames, ['Oferta.pdf', 'Drugi.pdf'])
  assert.equal(state.driveDialog.value, null)
})

test('failure to read an attachment prevents uploading and retains the selection', async () => {
  let uploaded = false
  const state = panel(async (path, method) => {
    if (path === '/access') return { read: true, add: true }
    if (path === '/folders') return []
    uploaded = true
  }, {}, () => {}, async () => ({ ok: false, json: async () => ({ detail: 'Nie można odczytać oryginału na IMAP.' }) }))
  state.messages.value = [message]; state.selectedId.value = message.id
  await state.openDriveDialog()
  await state.saveToDrive()
  assert.equal(uploaded, false)
  assert.equal(state.driveDialog.value.chosen.length, 1)
  assert.match(state.driveError.value, /odczytać/)
  assert.match(state.driveError.value, /IMAP/)
})

test('spam attachments cannot open drive picker or trigger downloading', async () => {
  let requested = false
  const state = panel(async () => { requested = true }, {}, () => {}, async () => { requested = true })
  state.messages.value = [{ ...message, folder: 'spam', attachments_blocked: true }]
  state.selectedId.value = message.id
  await state.download(message.attachments[0])
  await state.openDriveDialog(message.attachments[0])
  assert.equal(requested, false)
  assert.equal(state.driveDialog.value, null)
})

test('a message opened from the separate report uses its current folder and version', async () => {
  const calls = [], events = []
  const current = { ...message, folder: 'archive', version: 7 }
  const state = panel(async (path, method, body) => {
    calls.push({ path, method, body })
    if (path.startsWith('/client-mail?')) return [current]
    if (path === '/client-mail/settings') return {}
    return { ...current, ...body, version: 8 }
  }, { initialFolder: 'inbox', initialMessageId: 'one' }, (...args) => events.push(args))
  await state.mount()
  assert.equal(state.folder.value, 'archive')
  assert.equal(state.selected.value.id, 'one')
  assert.equal(calls.at(-1).body.version, 7)
  assert.equal(calls.at(-1).body.unread, false)
  assert.deepEqual(events.at(-1), ['message-opened'])
})

test('opening a removed report message shows an error and consumes the navigation request', async () => {
  const events = []
  const state = panel(async path => path.startsWith('/client-mail?') ? [] : {}, { initialMessageId: 'removed' }, (...args) => events.push(args))
  await state.mount()
  assert.match(state.error.value, /nie jest już dostępna/)
  assert.deepEqual(events.at(-1), ['message-opened'])
})


test('read-only admin preview loads and opens mail without scanning or changing unread state', async () => {
  const calls = []
  const state = panel(async (path, method) => {
    calls.push({ path, method })
    if (path.startsWith('/client-mail?')) return [{ ...message }]
    if (path === '/client-mail/settings') return { account: { imap: { enabled: false } } }
    return []
  }, { currentUser: { id: 'archived', impersonation: { read_only: true } } })
  await state.mount()
  await state.open(state.messages.value[0])
  await state.refresh()
  assert.equal(state.selectedId.value, message.id)
  assert.equal(state.messages.value[0].unread, 1)
  assert.equal(calls.some(call => call.method), false)
})
