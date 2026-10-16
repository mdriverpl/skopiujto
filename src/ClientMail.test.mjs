import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref, watch, reactive, nextTick } from 'vue'
import { mailSenderKind } from './mailSenderKind.js'

const compiled = compileScript(parse(readFileSync(new URL('./ClientMail.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'mail-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api, overrides = {}, emit = () => {}, fetcher = globalThis.fetch) {
  const mounted = []
  const context = { mailSenderKind, computed, ref, watch, onMounted(callback) { mounted.push(callback) }, FormData, fetch: fetcher, MailSettings: {} }
  for (const icon of ['Inbox', 'Send', 'FileText', 'Archive', 'ShieldAlert', 'Trash2', 'Handshake', 'Landmark', 'UserRound', 'Megaphone', 'Bell', 'Ban']) context[icon] = {}
  runInNewContext(compiled, context)
  const state = context.component.setup(reactive({ api, ...overrides }), { expose() {}, emit })
  state.mount = async () => { for (const callback of mounted) await callback() }
  return state
}
const message = { id: 'one', folder: 'inbox', sender_name: 'Jan Kowalski', sender_email: 'jan@example.com',
  recipient: 'ja@example.com', subject: 'Oferta', content: 'Warunki współpracy', unread: 1, label: 'urgent',
  version: 1, created_at: '2026-10-13T10:00:00Z', attachments: [{ id: 'a', name: 'Oferta.pdf' }] }

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
