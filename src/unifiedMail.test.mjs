import test from 'node:test'
import assert from 'node:assert/strict'
import { loadUnifiedMail, normalizeUnifiedMail, isEmailMessage, sourceKind } from './unifiedMail.js'

test('all channels retain the mailbox structure while native emails keep attachments and controls', () => {
  const native = { id: 'mail', subject: 'Oferta', version: 2, folder: 'inbox',
    attachments: [{ id: 'file', name: 'Umowa.pdf' }], company: { name: 'Firma' }, label: 'invoice' }
  const rows = normalizeUnifiedMail([
    { id: 'email:mail', source: 'email', source_id: 'mail', channel: 'email' },
    { id: 'internal:one', source: 'internal', source_id: 'one', channel: 'user', sender: 'Anna', recipient: 'Jan', title: 'Spotkanie', content: 'Przez portal', unread: true },
    { id: 'dispatch:one', source: 'dispatch', channel: 'sms', sender: 'Ja', recipient: 'Anna', title: 'SMS' }
  ], [native])
  assert.equal(rows[0].version, 2)
  assert.equal(rows[0].attachments[0].name, 'Umowa.pdf')
  assert.equal(rows[0].label, 'invoice')
  assert.equal(isEmailMessage(rows[0]), true)
  assert.equal(rows[1].subject, 'Spotkanie')
  assert.equal(rows[1].sender_email, '')
  assert.equal(rows[1].recipient, 'Jan')
  assert.equal(rows[1].unread, true)
  assert.equal(isEmailMessage(rows[1]), false)
  assert.equal(sourceKind(rows[1]), 'portal')
  assert.equal(sourceKind(rows[2]), 'sms')
})

test('unified received mail excludes spam and emails belonging to other folders', () => {
  const emails = [
    { id: 'folder-spam', folder: 'spam' },
    { id: 'category-spam', folder: 'inbox', category: 'spam' },
    { id: 'normal', folder: 'inbox' },
    { id: 'sent', folder: 'sent' },
    { id: 'draft', folder: 'drafts' },
    { id: 'archive', folder: 'archive' },
    { id: 'trash', folder: 'trash' }
  ]
  const rows = normalizeUnifiedMail(emails.map(email => ({ source: 'email', source_id: email.id })), emails)
  assert.deepEqual(rows.map(row => row.id), ['normal'])
})

test('received mail includes incoming channels and excludes outgoing channels', () => {
  const items = ['user', 'email', 'sms', 'edelivery'].flatMap(channel => ['incoming', 'outgoing'].map(direction => ({
    id: `${channel}:${direction}`, source: channel === 'edelivery' ? 'edelivery' : 'internal', channel, direction
  })))
  const rows = normalizeUnifiedMail(items, [])
  assert.equal(rows.length, 4)
  assert.ok(rows.every(row => row.center.direction === 'incoming'))
})

test('source is the delivery channel, and an emailed dispatch never enables native mailbox actions', () => {
  assert.equal(sourceKind({ center: { source: 'dispatch', channel: 'email' } }), 'email')
  assert.equal(isEmailMessage({ center: { source: 'dispatch', channel: 'email' } }), false)
  assert.equal(sourceKind({ center: { source: 'edelivery', channel: 'edelivery' } }), 'edelivery')
  assert.equal(sourceKind({ center: { source: 'unknown', channel: 'unknown' } }), 'other')
  assert.equal(sourceKind({ id: 'native-email' }), 'email')
})

test('loads every page of the unified history without limiting native mail actions to the last day', async () => {
  const calls = []
  const rows = await loadUnifiedMail(async path => {
    calls.push(path)
    if (path === '/client-mail?folder=inbox') return []
    const offset = Number(new URL('http://local' + path).searchParams.get('offset'))
    return { total: 205, items: Array.from({ length: Math.min(100, 205 - offset) }, (_, index) => ({
      id: `internal:${offset + index}`, source: 'internal', channel: 'user'
    })) }
  })
  assert.equal(rows.length, 205)
  assert.equal(rows.at(-1).id, 'internal:204')
  assert.equal(calls.includes('/client-mail?folder=inbox'), true)
  assert.equal(calls.some(path => path.includes('offset=200')), true)
  assert.ok(calls.filter(path => path.startsWith('/message-center?')).every(path => new URL('http://local' + path).searchParams.get('direction') === 'incoming'))
  assert.ok(calls.filter(path => path.startsWith('/message-center?')).every(path => new URL('http://local' + path).searchParams.get('include_native_email') === 'false'))
})

test('received emails come directly from the inbox without duplicate history entries', async () => {
  const native = { id: 'mail', folder: 'inbox', unread: true, attachments: [{ id: 'file' }], version: 3 }
  const rows = await loadUnifiedMail(async path => path === '/client-mail?folder=inbox' ? [native]
    : { items: [{ id: 'internal:one', source: 'internal', channel: 'user', direction: 'incoming' }], total: 1 })
  assert.equal(rows.length, 2)
  assert.equal(rows[0].id, 'mail')
  assert.equal(rows[0].center.id, 'email:mail')
  assert.equal(rows[0].center.direction, 'incoming')
  assert.equal(rows[0].version, 3)
  assert.equal(rows[0].attachments[0].id, 'file')
})
