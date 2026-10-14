import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'

const compiled = compileScript(parse(readFileSync(new URL('./ClientMail.vue', import.meta.url), 'utf8')).descriptor,
  { id: 'mail-test' }).content.replace(/^import .*$/gm, '').replace('export default', 'globalThis.component =')
function panel(api) {
  const context = { computed, ref, onMounted() {}, FormData, MailSettings: {} }
  for (const icon of ['Inbox', 'Send', 'FileText', 'Archive', 'ShieldAlert', 'Trash2']) context[icon] = {}
  runInNewContext(compiled, context)
  return context.component.setup({ api }, { expose() {} })
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
